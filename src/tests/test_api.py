import base64
import io
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db.models import Audit, Document, EmailJob, User
from app.db.session import SessionLocal
from app.core.config import settings
from app.services.email import process_email_jobs
from conftest import login


def application(name='Test United'):
    logo=io.BytesIO(); Image.new('RGB',(8,8),'green').save(logo,format='PNG')
    pdf=b'%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF'
    return {'teamName':name,'captain':'Captain','phone':'+27 71 234 5678','logo':{'name':'logo.png','type':'image/png','data':'data:image/png;base64,'+base64.b64encode(logo.getvalue()).decode()},'email':'captain@example.com','city':'Polokwane','players':[f'Player {i}' for i in range(5)],'prerequisitesAccepted':True,'proofOfPayment':{'name':'proof.pdf','type':'application/pdf','data':'data:application/pdf;base64,'+base64.b64encode(pdf).decode()}}


def test_auth_requires_rotation_csrf_logout_and_secure_headers(client):
    assert client.get('/api/v1/admin/bootstrap').status_code==401
    assert client.post('/api/v1/auth/login',json={'email':'admin@best5.co.za','password':'bad'}).status_code==401
    login(client,change=False)
    assert client.get('/api/v1/admin/users').status_code==403
    csrf=client.headers.pop('X-CSRF-Token')
    assert client.post('/api/v1/auth/change-password',json={'currentPassword':'TestInitialPassword!2026','newPassword':'ChangedTestPassword!2026'}).status_code==403
    client.headers['X-CSRF-Token']=csrf
    assert client.post('/api/v1/auth/change-password',json={'currentPassword':'TestInitialPassword!2026','newPassword':'ChangedTestPassword!2026'}).status_code==200
    response=client.get('/api/v1/admin/users')
    assert response.status_code==200
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['cache-control']=='no-store'
    cookie=client.cookies.get('best5_session')
    assert client.post('/api/v1/auth/logout',json={}).status_code==200
    client.cookies.set('best5_session',cookie)
    assert client.get('/api/v1/auth/me').status_code==401


def test_registration_private_pop_review_lookup_and_duplicate(client):
    response=client.post('/api/v1/registrations/team',json=application())
    assert response.status_code==201,response.text
    identifier=response.json()['id']
    assert client.post('/api/v1/registrations/team',json=application()).status_code==409
    public=client.get('/api/v1/public/bootstrap').json()['data']
    assert 'teamRegs' not in public
    assert public['teams']==[]
    assert client.post('/api/v1/registrations/lookup',json={'reference':identifier,'email':'wrong@example.com'}).status_code==404
    result=client.post('/api/v1/registrations/lookup',json={'reference':identifier,'email':'captain@example.com'}).json()
    assert result['status']=='Pending' and 'proofOfPayment' not in result and 'email' not in result
    login(client)
    data=client.get('/api/v1/admin/bootstrap').json()['data']
    proof=data['teamRegs'][0]['proofOfPayment']['data']
    assert client.get(proof).status_code==200
    with TestClient(app) as stranger:
        assert stranger.get(proof).status_code==401
    path=f'/api/v1/admin/registrations/team/{identifier}'
    assert client.patch(path,json={'status':'Approved','paymentStatus':'Under review','reviewNote':''}).status_code==422
    result=client.patch(path,json={'status':'Approved','paymentStatus':'Verified','reviewNote':'Welcome!'})
    assert result.status_code==200,result.text
    assert len(result.json()['data']['teams'])==1
    assert client.patch(path,json={'status':'Approved','paymentStatus':'Verified','reviewNote':'Welcome!'}).status_code==200
    assert len(client.get('/api/v1/public/bootstrap').json()['data']['teams'])==1
    assert client.post('/api/v1/registrations/lookup',json={'reference':identifier,'email':'captain@example.com'}).json()['status']=='Approved'
    with SessionLocal() as db:
        assert len(db.scalars(select(EmailJob)).all())==3
    assert client.get('/api/v1/admin/logs?category=registrations').json()['total']>=2


def test_registration_validates_files_and_disallows_forged_status(client):
    body=application(); body['proofOfPayment']['data']='data:application/pdf;base64,'+base64.b64encode(b'not a PDF').decode()
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    body=application(); body['status']='Approved'
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    body=application(); body['players']=['Same']*5
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    assert client.post('/api/v1/registrations/team',json=application(),headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/v1/auth/login',data='password=secret').status_code==415


def test_banking_password_required_no_generic_bypass_and_revision_conflicts(client):
    login(client)
    original=client.get('/api/v1/admin/bootstrap').json()
    bank={**original['data']['settings']['banking'],'bankName':'Updated bank'}
    response=client.put('/api/v1/admin/content/settings',json={'value':{**original['data']['settings'],'banking':bank},'revision':original['revisions']['settings']})
    assert response.status_code==403
    assert client.put('/api/v1/admin/settings/banking',json={'banking':bank,'password':'wrong'}).status_code==403
    response=client.put('/api/v1/admin/settings/banking',json={'banking':bank,'password':'ChangedTestPassword!2026'})
    assert response.status_code==200,response.text
    assert response.json()['data']['settings']['banking']['bankName']=='Updated bank'
    assert client.put('/api/v1/admin/content/settings',json={'value':original['data']['settings'],'revision':original['revisions']['settings']}).status_code==409


def test_rbac_staff_cannot_escalate_or_read_private_applications(client):
    login(client)
    created=client.post('/api/v1/admin/users',json={'email':'editor@example.com','name':'Editor','role':'editor','password':'EditorInitialPassword!2026'})
    assert created.status_code==201,created.text
    with TestClient(app) as editor:
        login(editor,'editor@example.com','EditorInitialPassword!2026')
        assert editor.get('/api/v1/admin/users').status_code==403
        assert editor.get('/api/v1/admin/logs').status_code==403
        assert 'teamRegs' not in editor.get('/api/v1/admin/bootstrap').json()['data']
        assert editor.put('/api/v1/admin/content/settings',json={'revision':0,'value':{}}).status_code==403
        assert editor.patch('/api/v1/admin/registrations/team/missing',json={'status':'Approved','paymentStatus':'Verified','reviewNote':''}).status_code==403
    identifier=created.json()['id']
    assert client.patch(f'/api/v1/admin/users/{identifier}',json={'role':'reviewer','active':False}).status_code==200
    assert client.patch(f'/api/v1/admin/users/{client.get("/api/v1/auth/me").json()["id"]}',json={'role':'editor','active':False}).status_code==422


def test_content_filtered_sanitized_and_saved_across_sessions(client):
    login(client)
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    posts=[{'id':'test-post','title':'Hello','slug':'hello','excerpt':'intro','content':'<p onclick="evil()">Safe</p><img src=x onerror=evil()>','date':'2026-11-03','status':'Draft','category':'News','featured':False,'image':''}]
    response=client.put('/api/v1/admin/content/posts',json={'revision':snapshot['revisions']['posts'],'value':posts})
    assert response.status_code==200,response.text
    assert 'onclick' not in response.json()['data']['posts'][0]['content']
    assert client.get('/api/v1/public/bootstrap').json()['data']['posts']==[]
    posts[0]['status']='Published'
    response=client.put('/api/v1/admin/content/posts',json={'revision':response.json()['revisions']['posts'],'value':posts})
    assert response.status_code==200
    with TestClient(app) as other:
        assert other.get('/api/v1/public/bootstrap').json()['data']['posts'][0]['title']=='Hello'


def test_email_queue_brevo_retry_and_no_body_in_logs(client,monkeypatch):
    import httpx
    client.post('/api/v1/registrations/team',json=application())
    monkeypatch.setattr(settings,'email_enabled',True)
    monkeypatch.setattr(settings,'brevo_api_key','test-key')
    monkeypatch.setattr(settings,'email_sender','sender@example.com')
    calls=[]
    def fail(url,**kwargs):
        calls.append(kwargs)
        return httpx.Response(503,request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',fail)
    process_email_jobs()
    with SessionLocal() as db:
        job=db.scalar(select(EmailJob)); assert job.status=='retry'; job.next_attempt=0; db.commit()
    def success(url,**kwargs):
        calls.append(kwargs)
        return httpx.Response(201,json={'messageId':'message-123'},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',success)
    process_email_jobs()
    assert calls[0]['headers']['api-key']=='test-key'
    assert calls[0]['json']['to']==[{'email':'captain@example.com'}]
    with SessionLocal() as db:
        job=db.scalar(select(EmailJob)); assert job.status=='sent' and job.provider_id=='message-123' and job.body==''
        messages=' '.join(x.message for x in db.scalars(select(Audit)))
        assert 'test-key' not in messages and 'captain@example.com' not in messages


def test_password_reset_is_single_use_and_revokes_sessions(client):
    login(client)
    response=client.post('/api/v1/auth/forgot-password',json={'email':'admin@best5.co.za'})
    missing=client.post('/api/v1/auth/forgot-password',json={'email':'missing@example.com'})
    assert response.json()==missing.json()
    with SessionLocal() as db:
        body=db.scalar(select(EmailJob).where(EmailJob.subject=='Reset your BEST5 password')).body
    raw=body.split('token=')[1]
    response=client.post('/api/v1/auth/reset-password',json={'token':raw,'password':'ResetNewPassword!2026'})
    assert response.status_code==200,response.text
    assert client.get('/api/v1/auth/me').status_code==401
    assert client.post('/api/v1/auth/reset-password',json={'token':raw,'password':'ResetNewPassword!2026'}).status_code==400


def test_capacity_is_enforced_under_concurrent_approval(client):
    ids=[client.post('/api/v1/registrations/team',json=application(f'United {i}')).json()['id'] for i in range(3)]
    login(client)
    snap=client.get('/api/v1/admin/bootstrap').json()
    assert client.put('/api/v1/admin/content/settings',json={'revision':snap['revisions']['settings'],'value':{'numberOfTeams':2}}).status_code==200
    assert client.patch(f'/api/v1/admin/registrations/team/{ids[0]}',json={'status':'Approved','paymentStatus':'Verified','reviewNote':''}).status_code==200
    # Separate DB connections and requests compete for the final place.
    clients=[TestClient(app),TestClient(app)]
    for c in clients:
        c.cookies.update(client.cookies); c.headers['X-CSRF-Token']=client.headers['X-CSRF-Token']
    def approve(pair):
        c,identifier=pair
        return c.patch(f'/api/v1/admin/registrations/team/{identifier}',json={'status':'Approved','paymentStatus':'Verified','reviewNote':''}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(approve,zip(clients,ids[1:])))
    assert sorted(statuses)==[200,409],statuses
    assert len(client.get('/api/v1/public/bootstrap').json()['data']['teams'])==2


def test_fixtures_groups_scores_conflicts_and_approval_reversal(client):
    ids=[client.post('/api/v1/registrations/team',json=application(f'Match Team {i}')).json()['id'] for i in range(2)]
    login(client)
    for identifier in ids:
        response=client.patch(f'/api/v1/admin/registrations/team/{identifier}',json={'status':'Approved','paymentStatus':'Verified','reviewNote':''})
        assert response.status_code==200,response.text
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    teams=snapshot['data']['teams']
    for team in teams: team['group']='Group A'
    response=client.put('/api/v1/admin/content/teams',json={'value':teams,'revision':snapshot['revisions']['teams']})
    assert response.status_code==200,response.text
    snapshot=response.json()
    fixture={'id':'fixture-1','homeId':teams[0]['id'],'awayId':teams[0]['id'],'date':'2026-12-12','time':'09:00','pitch':'Pitch 1','stage':'Group Stage','group':'Group A','status':'Full Time','homeScore':2,'awayScore':1}
    response=client.put('/api/v1/admin/content/fixtures',json={'value':[fixture],'revision':snapshot['revisions']['fixtures']})
    assert response.status_code==422
    fixture['awayId']=teams[1]['id']
    response=client.put('/api/v1/admin/content/fixtures',json={'value':[fixture],'revision':snapshot['revisions']['fixtures']})
    assert response.status_code==200,response.text
    snapshot=response.json()
    duplicate={**fixture,'id':'fixture-2'}
    assert client.put('/api/v1/admin/content/fixtures',json={'value':[fixture,duplicate],'revision':snapshot['revisions']['fixtures']}).status_code==409
    assert client.patch(f'/api/v1/admin/registrations/team/{ids[0]}',json={'status':'Rejected','paymentStatus':'Verified','reviewNote':'Withdrawn'}).status_code==409
    teams[0]['group']='Group B'
    assert client.put('/api/v1/admin/content/teams',json={'value':teams,'revision':snapshot['revisions']['teams']}).status_code==422


def test_login_rate_limit_and_validation_does_not_echo_password(client,monkeypatch):
    monkeypatch.setattr(settings,'rate_limit_enabled',True)
    from app.main import create_app
    with TestClient(create_app()) as limited:
        for _ in range(10):
            assert limited.post('/api/v1/auth/login',json={'email':'admin@best5.co.za','password':'wrong'}).status_code==401
        response=limited.post('/api/v1/auth/login',json={'email':'admin@best5.co.za','password':'wrong'})
        assert response.status_code==429 and response.headers['retry-after']=='60'
    response=client.post('/api/v1/auth/login',json={'email':'invalid','password':'never-echo-this-password'})
    assert response.status_code==422 and 'never-echo-this-password' not in response.text


def test_media_images_are_verified_persisted_and_served_publicly(client):
    import io
    from PIL import Image
    buffer=io.BytesIO(); Image.new('RGB',(2,2),'green').save(buffer,format='PNG')
    image='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
    login(client)
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    media=[{'id':'image-1','name':'Team image','src':image,'type':'image/png','category':'General','createdAt':'2026-11-03T12:00:00Z'}]
    response=client.put('/api/v1/admin/content/media',json={'value':media,'revision':snapshot['revisions']['media']})
    assert response.status_code==200,response.text
    source=response.json()['data']['media'][0]['src']
    assert source.startswith('/api/v1/files/') and 'base64' not in source
    with TestClient(app) as public:
        image_response=public.get(source)
        assert image_response.status_code==200 and image_response.content==buffer.getvalue()
    media[0]['src']='data:image/png;base64,'+base64.b64encode(b'not a PNG').decode()
    response=client.put('/api/v1/admin/content/media',json={'value':media,'revision':response.json()['revisions']['media']})
    assert response.status_code==422


def test_super_admin_owns_staff_and_logs_while_admin_keeps_operations(client):
    login(client)
    me=client.get('/api/v1/auth/me').json()
    assert me['role']=='super_admin' and 'users:manage' in me['permissions']
    created=client.post('/api/v1/admin/users',json={'email':'ordinary-admin@example.com','name':'Tournament Admin','role':'admin','password':'AdminInitialPassword!2026'})
    assert created.status_code==201,created.text
    with TestClient(app) as admin:
        login(admin,'ordinary-admin@example.com','AdminInitialPassword!2026')
        me=admin.get('/api/v1/auth/me').json()
        assert me['role']=='admin' and 'logs:read' not in me['permissions'] and 'users:manage' not in me['permissions']
        for path in ['/api/v1/admin/users','/api/v1/admin/logs','/api/v1/admin/request-logs','/api/v1/admin/email-jobs']:
            assert admin.get(path).status_code==403,path
        assert admin.post('/api/v1/admin/users',json={'email':'forged@example.com','name':'Forbidden','role':'super_admin','password':'ForbiddenPassword!2026'}).status_code==403
        snapshot=admin.get('/api/v1/admin/bootstrap').json()
        assert 'teamRegs' in snapshot['data'] and 'activity' not in snapshot['data']
        response=admin.put('/api/v1/admin/content/settings',json={'revision':snapshot['revisions']['settings'],'value':{'venue':'Admin managed venue'}})
        assert response.status_code==200,response.text


def test_initial_admin_promotion_is_once_and_preserves_password(client):
    from app.db.models import User
    from app.services.initial_admin import MARKER, promote_initial_admin
    with SessionLocal() as db:
        original=db.scalar(select(User).where(User.email=='admin@best5.co.za'))
        password_hash=original.password_hash
        db.delete(db.get(Document,MARKER)); original.role='admin'; db.commit()
        promote_initial_admin(db); db.commit(); db.refresh(original)
        assert original.role=='super_admin' and original.password_hash==password_hash
        assert db.get(Document,MARKER).value['userId']==original.id
        # A later deliberate role change must never be undone by startup.
        original.role='manager'; db.commit()
        promote_initial_admin(db); db.commit(); db.refresh(original)
        assert original.role=='manager'


def test_login_cannot_choose_or_override_role(client):
    body={'email':'admin@best5.co.za','password':'TestInitialPassword!2026','role':'super_admin'}
    assert client.post('/api/v1/auth/login',json=body).status_code==422


def test_sibling_domain_login_csrf_and_logout(client, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setattr(settings,'trusted_hosts',['api.best5football.co.za'])
    monkeypatch.setattr(settings,'cors_origins',['https://best5football.co.za'])
    monkeypatch.setattr(settings,'csrf_cookie_domain','best5football.co.za')
    sibling=TestClient(create_app(),base_url='https://api.best5football.co.za')
    origin={'Origin':'https://best5football.co.za'}
    result=sibling.post('/api/v1/auth/login',headers=origin,json={'email':'admin@best5.co.za','password':'TestInitialPassword!2026','remember':True})
    assert result.status_code==200
    cookies=result.headers.get_list('set-cookie')
    assert any('best5_csrf=' in item and 'Domain=best5football.co.za' in item for item in cookies)
    assert all('Domain=' not in item for item in cookies if item.startswith('best5_session='))
    csrf=sibling.cookies.get('best5_csrf')
    headers={**origin,'X-CSRF-Token':csrf}
    changed=sibling.post('/api/v1/auth/change-password',headers=headers,json={'currentPassword':'TestInitialPassword!2026','newPassword':'DomainLoginPassword!2026'})
    assert changed.status_code==200
    result=sibling.post('/api/v1/auth/logout',headers=headers,json={})
    assert result.status_code==200
    assert any('best5_csrf=' in item and 'Domain=best5football.co.za' in item and 'Max-Age=0' in item for item in result.headers.get_list('set-cookie'))
    assert sibling.get('/api/v1/auth/me').status_code==401


def test_preview_proxy_login_retains_host_only_csrf_with_production_domain_configured(client, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setattr(settings,'csrf_cookie_domain','best5football.co.za')
    monkeypatch.setattr(settings,'cors_origins',['https://football-exhibition-cms.vercel.app'])
    preview=TestClient(create_app())
    headers={'Origin':'https://football-exhibition-cms.vercel.app'}
    result=preview.post('/api/v1/auth/login',headers=headers,json={'email':'admin@best5.co.za','password':'TestInitialPassword!2026','remember':True})
    assert result.status_code==200
    assert all('Domain=' not in item for item in result.headers.get_list('set-cookie'))
    headers['X-CSRF-Token']=preview.cookies.get('best5_csrf')
    result=preview.post('/api/v1/auth/change-password',headers=headers,json={'currentPassword':'TestInitialPassword!2026','newPassword':'PreviewPassword!2026'})
    assert result.status_code==200
    result=preview.post('/api/v1/auth/logout',headers=headers,json={})
    assert result.status_code==200
    assert all('Domain=' not in item for item in result.headers.get_list('set-cookie'))


def test_registration_logo_is_verified_and_promoted_to_public_team(client):
    import io
    from PIL import Image
    output=io.BytesIO()
    Image.new('RGB',(8,8),'green').save(output,format='PNG')
    body=application('Logo United')
    body['logo']={'name':'team.png','type':'image/png','data':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()}
    result=client.post('/api/v1/registrations/team',json=body)
    assert result.status_code==201,result.text
    identifier=result.json()['id']
    assert client.get('/api/v1/public/bootstrap').json()['data']['teams']==[]
    login(client)
    record=client.get('/api/v1/admin/bootstrap').json()['data']['teamRegs'][0]
    logo=record['logo']
    assert logo.startswith('/api/v1/files/')
    review={'status':'Approved','paymentStatus':'Verified','reviewNote':''}
    result=client.patch(f'/api/v1/admin/registrations/team/{identifier}',json=review)
    assert result.status_code==200
    assert result.json()['data']['teams'][0]['logo']==logo
    with TestClient(app) as public:
        teams=public.get('/api/v1/public/bootstrap').json()['data']['teams']
        assert teams[0]['logo']==logo
        image=public.get(logo)
        assert image.status_code==200 and image.headers['content-type'].startswith('image/png')
        assert image.content==output.getvalue()
        assert public.get(record['proofOfPayment']['data']).status_code==401


def test_registration_rejects_invalid_and_oversized_logos(client,monkeypatch):
    body=application()
    body['logo']={'name':'fake.png','type':'image/png','data':'data:image/png;base64,'+base64.b64encode(b'not a real image').decode()}
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    body['logo']['type']='image/svg+xml'
    assert client.post('/api/v1/registrations/team',json=body).status_code==422
    monkeypatch.setattr(settings,'max_branding_image_size_mb',1)
    body['logo']={'name':'large.png','type':'image/png','data':'data:image/png;base64,'+base64.b64encode(b'x'*(1024*1024+1)).decode()}
    assert client.post('/api/v1/registrations/team',json=body).status_code==422


def test_team_and_vendor_registration_queue_status_emails(client):
    team=client.post('/api/v1/registrations/team',json=application('Email United'))
    vendor=client.post('/api/v1/registrations/vendor',json={'business':'Food & Friends','contact':'Vendor Captain','category':'Food & Drinks','email':'vendor@example.com','description':'Fresh food on matchday.'})
    assert team.status_code==201 and vendor.status_code==201
    with SessionLocal() as db:
        jobs=db.scalars(select(EmailJob)).all()
        assert len(jobs)==4
        for response,recipient in [(team,'captain@example.com'),(vendor,'vendor@example.com')]:
            job=next(job for job in jobs if job.recipient==recipient)
            reference=response.json()['id']
            assert reference in job.body and reference in job.html_body
            assert 'Check application status' in job.html_body
            assert '/application-status#reference=' in job.html_body
            assert job.status=='pending'


def test_sponsor_logos_save_and_are_public(client):
    login(client)
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    landing=snapshot['data']['landing']
    landing['sponsorLogos']=[{'id':'test-sponsor','name':'Test Sponsor','image':'/assets/images/sponsors/aquelle.png','scale':1.2}]
    response=client.put('/api/v1/admin/content/landing',json={'value':landing,'revision':snapshot['revisions']['landing']})
    assert response.status_code==200,response.text
    assert client.get('/api/v1/public/bootstrap').json()['data']['landing']['sponsorLogos'][0]['name']=='Test Sponsor'


def test_sponsor_save_supports_landing_documents_created_before_sponsors(client):
    # Existing production records lack fields introduced after their first seed.
    with SessionLocal() as db:
        landing=db.get(Document,'landing')
        old=dict(landing.value)
        old.pop('sponsorLogos',None)
        old['heroEyebrow']='Keep my existing headline'
        landing.value=old
        db.commit()
    login(client)
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    value=dict(snapshot['data']['landing'])
    value['sponsorLogos']=[{'id':'new-sponsor','name':'New partner','image':'/assets/images/sponsors/aquelle.png','scale':1}]
    response=client.put('/api/v1/admin/content/landing',json={'revision':snapshot['revisions']['landing'],'value':value})
    assert response.status_code==200,response.text
    public=client.get('/api/v1/public/bootstrap').json()['data']['landing']
    assert public['sponsorLogos']==value['sponsorLogos']
    assert public['heroEyebrow']=='Keep my existing headline'
    current=response.json()
    value['unsupportedField']='still rejected'
    assert client.put('/api/v1/admin/content/landing',json={'revision':current['revisions']['landing'],'value':value}).status_code==422


def test_vendor_fees_follow_category_and_are_stored_and_emailed(client):
    categories=['Food & Drinks','Clothing & Accessories','Lifestyle & Services','Brand Activations']
    for index,category in enumerate(categories):
        body={'business':f'Stall {index}','contact':'Vendor','category':category,'email':f'vendor{index}@example.com','description':'Matchday stall.'}
        response=client.post('/api/v1/registrations/vendor',json=body)
        assert response.status_code==201,response.text
        expected=1000 if index==0 else 350
        assert response.json()['stallFee']==expected
        identifier=response.json()['id']
        with SessionLocal() as db:
            from app.db.models import Record
            assert db.get(Record,identifier).value['stallFee']==expected
            job=db.scalar(select(EmailJob).where(EmailJob.recipient==body['email']))
            assert f'R{expected:,.0f}' in job.body and f'R{expected:,.0f}' in job.html_body
        body['stallFee']=1
        assert client.post('/api/v1/registrations/vendor',json=body).status_code==422


def test_existing_settings_accept_food_fee_and_posts_keep_saved_order(client):
    with SessionLocal() as db:
        row=db.get(Document,'settings');value=dict(row.value);value.pop('vendorFoodStallFee',None);row.value=value;db.commit()
    login(client)
    snapshot=client.get('/api/v1/admin/bootstrap').json()
    response=client.put('/api/v1/admin/content/settings',json={'revision':snapshot['revisions']['settings'],'value':{'vendorFoodStallFee':1000}})
    assert response.status_code==200,response.text
    posts=list(reversed(snapshot['data']['posts']))
    response=client.put('/api/v1/admin/content/posts',json={'revision':snapshot['revisions']['posts'],'value':posts})
    assert response.status_code==200,response.text
    assert [p['id'] for p in client.get('/api/v1/public/bootstrap').json()['data']['posts']]==[p['id'] for p in posts if p['status']=='Published']


def test_team_requires_logo_and_phone_and_retains_phone_privately(client):
    for field in ('logo', 'phone'):
        body=application(); body.pop(field)
        assert client.post('/api/v1/registrations/team',json=body).status_code==422
    for phone in ('abc1234', '123', '+27+712345678', ' ' * 8):
        body=application(); body['phone']=phone
        assert client.post('/api/v1/registrations/team',json=body).status_code==422
    result=client.post('/api/v1/registrations/team',json=application())
    assert result.status_code==201
    lookup=client.post('/api/v1/registrations/lookup',json={'reference':result.json()['id'],'email':'captain@example.com'})
    assert 'phone' not in lookup.json()
    login(client)
    assert client.get('/api/v1/admin/bootstrap').json()['data']['teamRegs'][0]['phone']=='+27 71 234 5678'


def test_submission_notifications_only_go_to_active_admin_roles(client):
    from uuid import uuid4
    with SessionLocal() as db:
        for role, active in [('admin', True), ('admin', False), ('editor', True), ('reviewer', True)]:
            db.add(User(id=str(uuid4()),name=role,email=f'{role}-{active}@example.com',role=role,active=active,password_hash='unused'))
        db.commit()
    responses=[client.post('/api/v1/registrations/team',json=application()),
               client.post('/api/v1/registrations/vendor',json={'business':'Vendor <test>','contact':'Person','category':'Food & Drinks','email':'vendor@example.com','description':'Food'})]
    assert all(response.status_code==201 for response in responses)
    with SessionLocal() as db:
        jobs=db.scalars(select(EmailJob).where(EmailJob.subject.like('BEST5 new %'))).all()
        assert len(jobs)==4
        assert {job.recipient for job in jobs}=={'admin@best5.co.za','admin-True@example.com'.lower()}
        for job in jobs:
            assert 'Review applications' in job.html_body
            assert '/admin/' in job.html_body and '-registrations' in job.html_body
            assert 'data:application' not in job.html_body
        team_job=next(job for job in jobs if 'new team' in job.subject)
        assert '+27 71 234 5678' in team_job.body
        vendor_job=next(job for job in jobs if 'new vendor' in job.subject)
        assert 'Vendor &lt;test&gt;' in vendor_job.html_body
