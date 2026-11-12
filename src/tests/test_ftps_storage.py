import base64
import io
from ftplib import error_perm
import ssl
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select
from app.core.config import Settings, settings
from app.db.models import Record, Upload
from app.db.session import SessionLocal
from app.services import ftps_storage
from conftest import login


class FakeFTP:
    files = {}
    directories = {'/'}
    actions = []

    def __init__(self,context,timeout):
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        self.directory = '/'
    def connect(self,host,port): self.actions.append(('connect',host,port))
    def auth(self): self.actions.append(('auth',))
    def login(self,user,password): self.actions.append(('login',user))
    def prot_p(self): self.actions.append(('encrypted-data',))
    def set_pasv(self,value): assert value
    def close(self): self.actions.append(('close',))
    def cwd(self,path):
        directory = path if path.startswith('/') else self.directory.rstrip('/')+'/'+path
        if directory not in self.directories: raise error_perm('550 Missing directory')
        self.directory = directory
    def mkd(self,path): self.directories.add(self.directory.rstrip('/')+'/'+path)
    def key(self,name): return self.directory.rstrip('/')+'/'+name
    def storbinary(self,command,source): self.files[self.key(command.removeprefix('STOR '))] = source.read()
    def rename(self,old,new): self.files[self.key(new)] = self.files.pop(self.key(old))
    def delete(self,name): self.files.pop(self.key(name),None)
    def retrbinary(self,command,callback):
        key = self.key(command.removeprefix('RETR '))
        if key not in self.files: raise error_perm('550 Missing file')
        callback(self.files[key])


@pytest.fixture
def remote(monkeypatch):
    ftps_storage.clear_public_cache()
    FakeFTP.files = {}; FakeFTP.directories = {'/'}; FakeFTP.actions = []
    monkeypatch.setattr(ftps_storage,'SecureFTP',FakeFTP)
    monkeypatch.setattr(settings,'upload_storage','ftps')
    monkeypatch.setattr(settings,'ftps_host','ftp.example.com')
    monkeypatch.setattr(settings,'ftps_username','uploads@example.com')
    monkeypatch.setattr(settings,'ftps_password',SecretStr('private-test-password'))
    monkeypatch.setattr(settings,'ftps_root','/')
    return FakeFTP


def application():
    image=io.BytesIO(); Image.new('RGB',(8,8),'green').save(image,format='PNG')
    pdf=b'%PDF-1.4\n%%EOF'
    return {'teamName':'Remote United','captain':'Captain','phone':'+27 71 234 5678','email':'captain@example.com','city':'Polokwane','players':[f'Player {i}' for i in range(5)],'prerequisitesAccepted':True,
            'logo':{'name':'logo.png','type':'image/png','data':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()},
            'proofOfPayment':{'name':'proof.pdf','type':'application/pdf','data':'data:application/pdf;base64,'+base64.b64encode(pdf).decode()}}


def test_remote_uploads_survive_new_local_directory_and_keep_pop_private(client,remote,monkeypatch,tmp_path):
    result=client.post('/api/v1/registrations/team',json=application())
    assert result.status_code==201,result.text
    login(client)
    record=client.get('/api/v1/admin/bootstrap').json()['data']['teamRegs'][0]
    logo,proof=record['logo'],record['proofOfPayment']['data']
    assert len(remote.files)==2 and not any(name.endswith('.part') for name in remote.files)
    assert any(name.startswith('/public/') for name in remote.files)
    assert any(name.startswith('/private/') for name in remote.files)
    assert [action[0] for action in remote.actions[:4]]==['connect','auth','login','encrypted-data']
    monkeypatch.setattr(settings,'branding_path',tmp_path/'empty-images')
    monkeypatch.setattr(settings,'storage_dir',tmp_path/'empty-documents')
    assert client.get(logo).status_code==200
    response=client.get(proof)
    assert response.status_code==200 and response.content.startswith(b'%PDF-')
    assert response.headers['cache-control']=='private, no-store'
    assert 'attachment' in response.headers['content-disposition']
    client.cookies.clear()
    before=len(remote.actions)
    assert client.get(proof).status_code==401
    assert len(remote.actions)==before  # Permission is checked before accessing the FTP server.
    assert client.get(logo).status_code==200


def test_failed_remote_write_is_not_reported_saved_or_written_locally(client,remote,monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'branding_path',tmp_path/'images')
    def fail(self,command,source):
        self.files[self.key(command.removeprefix('STOR '))]=b'partial'
        raise OSError('contains-private-test-password')
    monkeypatch.setattr(remote,'storbinary',fail)
    result=client.post('/api/v1/registrations/team',json=application())
    assert result.status_code==503 and 'password' not in result.text
    assert not remote.files and not (tmp_path/'images').exists()
    with SessionLocal() as db:
        assert db.scalar(select(Record)) is None
        assert db.scalar(select(Upload)) is None


def test_invalid_image_never_reaches_remote_storage(client,remote):
    body=application();body['logo']['data']='data:image/png;base64,'+base64.b64encode(b'fake').decode()
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    assert remote.actions==[]


def test_tls_failure_does_not_send_credentials(client,remote,monkeypatch):
    def fail(self):
        self.actions.append(('auth',))
        raise ssl.SSLCertVerificationError('untrusted certificate')
    monkeypatch.setattr(remote,'auth',fail)
    assert client.post('/api/v1/registrations/team',json=application()).status_code==503
    assert not any(action[0]=='login' for action in remote.actions)


def test_remote_download_limits_and_missing_files(remote,monkeypatch):
    identifier=str(uuid4())
    assert ftps_storage.retrieve(identifier,False) is None
    remote.directories.add('/public');remote.files['/public/'+identifier]=b'too big'
    monkeypatch.setattr(ftps_storage,'MAX_STORED_FILE_BYTES',3)
    with pytest.raises(Exception) as error:
        ftps_storage.retrieve(identifier,False)
    assert error.value.status_code==503
    with pytest.raises(Exception) as error:
        ftps_storage.retrieve('../private/file',False)
    assert error.value.status_code==404


def test_ftps_configuration_requires_credentials_and_confines_paths():
    with pytest.raises(ValueError): Settings(_env_file=None,upload_storage='ftps')
    config=Settings(_env_file=None,upload_storage='ftps',ftps_host='ftp.example.com',ftps_username='uploads',ftps_password='test-secret-value')
    assert config.ftps_port==21 and config.ftps_root=='/'
    assert 'test-secret-value' not in repr(config)
    for root in ('../public','/../public','/private\r\nDELE file'):
        with pytest.raises(ValueError): Settings(_env_file=None,ftps_root=root)


def test_data_channel_reuses_verified_tls_session(monkeypatch):
    ftp=ftps_storage.SecureFTP(context=ssl.create_default_context())
    raw=Mock();encrypted=Mock();session=object()
    ftp.host='ftp.example.com';ftp.sock=SimpleNamespace(session=session);ftp._prot_p=True
    ftp.context=Mock();ftp.context.wrap_socket.return_value=encrypted
    monkeypatch.setattr(ftps_storage.FTP,'ntransfercmd',lambda *args:(raw,42))
    assert ftp.ntransfercmd('RETR file')==(encrypted,42)
    ftp.context.wrap_socket.assert_called_once_with(raw,server_hostname='ftp.example.com',session=session)


def test_public_cache_avoids_repeat_ftp_and_never_caches_private(remote, monkeypatch):
    public, private = str(uuid4()), str(uuid4())
    remote.directories.update({'/public', '/private'})
    remote.files.update({'/public/'+public: b'image', '/private/'+private: b'proof'})
    for identifier, is_private in ((public, False), (public, False), (private, True), (private, True)):
        with ftps_storage.retrieve(identifier, is_private) as stream:
            assert stream.read() == (b'proof' if is_private else b'image')
    assert sum(action[0] == 'connect' for action in remote.actions) == 3
    monkeypatch.setattr(ftps_storage, 'PUBLIC_CACHE_BYTES', 6)
    ftps_storage.cache_public(str(uuid4()), b'new')
    assert sum(map(len, ftps_storage._PUBLIC_CACHE.values())) <= 6
    assert private not in ftps_storage._PUBLIC_CACHE
