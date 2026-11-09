import importlib.util
from pathlib import Path
from zipfile import ZipFile
import httpx

spec=importlib.util.spec_from_file_location('backup_uploads',Path(__file__).resolve().parents[1]/'scripts/backup_uploads.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PUBLIC='11111111-1111-4111-8111-111111111111'
PRIVATE='22222222-2222-4222-8222-222222222222'
MISSING='33333333-3333-4333-8333-333333333333'


def test_backup_keeps_ids_private_files_and_records_missing_uploads(tmp_path):
    calls=[]
    snapshot={'data':{'media':[{'src':f'/api/v1/files/{PUBLIC}'},{'src':f'/api/v1/files/{MISSING}'}],
                      'teamRegs':[{'proofOfPayment':{'data':f'https://api.example.com/api/v1/files/{PRIVATE}'}}]}}
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/auth/login'):
            return httpx.Response(200,json={'permissions':['content:read','operations:read'],'mustChangePassword':False},headers={'set-cookie':'best5_csrf=test-token; Path=/; Secure'})
        if request.url.path.endswith('/admin/bootstrap'): return httpx.Response(200,json=snapshot)
        if request.url.path.endswith('/auth/logout'):
            assert request.headers['x-csrf-token']=='test-token'
            return httpx.Response(200,json={})
        if request.url.path.endswith(PUBLIC): return httpx.Response(200,content=b'image-bytes',headers={'content-type':'image/png'})
        if request.url.path.endswith(PRIVATE): return httpx.Response(200,content=b'%PDF-proof',headers={'content-type':'application/pdf'})
        return httpx.Response(404,json={'detail':'File unavailable'})
    folder,archive,saved,failed=module.backup('https://api.example.com/api/v1','https://example.com','owner@example.com','do-not-save-password',tmp_path,httpx.MockTransport(handler))
    assert saved==2 and failed==1
    assert (folder/'public'/PUBLIC).read_bytes()==b'image-bytes'
    assert (folder/'private'/PRIVATE).read_bytes()==b'%PDF-proof'
    assert calls[-1].endswith('/auth/logout')
    with ZipFile(archive) as package:
        assert f'public/{PUBLIC}' in package.namelist() and f'private/{PRIVATE}' in package.namelist()
        assert b'do-not-save-password' not in package.read('admin-snapshot.json')
    assert archive.stat().st_mode & 0o777==0o600


def test_backup_does_not_store_html_in_place_of_a_missing_image(tmp_path):
    def handler(request):
        if request.url.path.endswith('/auth/login'): return httpx.Response(200,json={'permissions':['content:read','operations:read']})
        if request.url.path.endswith('/admin/bootstrap'): return httpx.Response(200,json={'data':{'image':f'/api/v1/files/{PUBLIC}'}})
        if request.url.path.endswith('/auth/logout'): return httpx.Response(200,json={})
        return httpx.Response(200,text='<html>Not an image</html>',headers={'content-type':'text/html'})
    folder,archive,saved,failed=module.backup('https://api.example.com/api/v1','https://example.com','owner@example.com','password',tmp_path,httpx.MockTransport(handler))
    assert saved==0 and failed==1
    assert not (folder/'public'/PUBLIC).exists()
