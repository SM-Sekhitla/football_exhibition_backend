from urllib.parse import parse_qs,urlsplit
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.main import app
from src.db.models import EmailJob,StaffInvitation,User
from src.db.session import SessionLocal
from src.core.security import digest,now
from src.core.config import settings
from src.services.email import process_email_jobs
from src.services.invitations import SUBJECT
from conftest import login


def invitation_token():
    with SessionLocal() as db:
        job=db.scalar(select(EmailJob).where(EmailJob.subject==SUBJECT,EmailJob.status=='pending').order_by(EmailJob.next_attempt.desc()))
        link=next(line for line in job.body.splitlines() if '/admin/accept-invitation#' in line)
        return parse_qs(urlsplit(link).fragment)['token'][0],job.id


def create(client,email='invited@example.com'):
    response=client.post('/api/v1/admin/users',json={'email':email,'name':'Invited Reviewer','role':'reviewer'})
    assert response.status_code==201,response.text
    return response.json()


def test_invite_sets_own_password_and_logs_in_with_assigned_role(client):
    login(client)
    result=create(client)
    assert result['invitation']['status']=='Pending' and result['invitation']['emailStatus']=='pending'
    assert 'disabled' in result['message']
    raw,job_id=invitation_token()
    assert raw not in str(result)
    with SessionLocal() as db:
        invitation=db.scalar(select(StaffInvitation))
        assert invitation.id==digest(raw) and invitation.id!=raw
    with TestClient(app) as person:
        response=person.post('/api/v1/auth/accept-invitation',json={'token':raw,'password':'MyOwnPassword!2026'})
        assert response.status_code==200,response.text
        assert person.post('/api/v1/auth/accept-invitation',json={'token':raw,'password':'AnotherPassword!2026'}).status_code==400
        response=person.post('/api/v1/auth/login',json={'email':'invited@example.com','password':'MyOwnPassword!2026'})
        assert response.status_code==200,response.text
        assert response.json()['role']=='reviewer' and not response.json()['mustChangePassword']
        assert person.get('/api/v1/admin/logs').status_code==403
    with SessionLocal() as db:
        job=db.get(EmailJob,job_id)
        assert job.status=='cancelled' and job.body==''


def test_resend_revokes_previous_link_and_old_temporary_password(client):
    login(client)
    response=client.post('/api/v1/admin/users',json={'email':'old@example.com','name':'Existing Staff','role':'editor','password':'OldTemporaryPassword!2026'})
    assert response.status_code==201
    identifier=response.json()['id'];old,old_job=invitation_token()
    assert client.post(f'/api/v1/admin/users/{identifier}/invitation',json={}).status_code==200
    new,new_job=invitation_token();assert new!=old and new_job!=old_job
    with TestClient(app) as person:
        assert person.post('/api/v1/auth/accept-invitation',json={'token':old,'password':'MyOwnPassword!2026'}).status_code==400
        assert person.post('/api/v1/auth/login',json={'email':'old@example.com','password':'OldTemporaryPassword!2026'}).status_code==401
        assert person.post('/api/v1/auth/accept-invitation',json={'token':new,'password':'MyOwnPassword!2026'}).status_code==200
    assert client.post(f'/api/v1/admin/users/{identifier}/invitation',json={}).status_code==409


def test_expired_and_deactivated_invites_cannot_be_used(client):
    login(client);row=create(client)
    raw,job_id=invitation_token()
    with SessionLocal() as db:
        db.get(StaffInvitation,digest(raw)).expires=now()-1;db.commit()
    assert client.post('/api/v1/auth/accept-invitation',json={'token':raw,'password':'MyOwnPassword!2026'}).status_code==400
    client.post(f'/api/v1/admin/users/{row["id"]}/invitation',json={})
    raw,_=invitation_token()
    assert client.patch(f'/api/v1/admin/users/{row["id"]}',json={'role':'reviewer','active':False}).status_code==200
    assert client.post('/api/v1/auth/accept-invitation',json={'token':raw,'password':'MyOwnPassword!2026'}).status_code==400


def test_expired_invitation_is_not_sent_by_email_worker(client,monkeypatch):
    login(client);create(client);raw,job_id=invitation_token()
    with SessionLocal() as db:
        db.get(StaffInvitation,digest(raw)).expires=now()-1;db.commit()
    monkeypatch.setattr(settings,'email_enabled',True)
    import httpx
    def do_not_send(*args,**kwargs): raise AssertionError('Expired invitation must not be sent')
    monkeypatch.setattr(httpx,'post',do_not_send)
    process_email_jobs()
    with SessionLocal() as db:
        assert db.get(EmailJob,job_id).status=='expired'


def test_only_super_admin_can_resend_invitations(client):
    login(client);row=create(client)
    with TestClient(app) as stranger:
        assert stranger.post(f'/api/v1/admin/users/{row["id"]}/invitation',json={}).status_code==401
    csrf=client.headers['X-CSRF-Token']
    client.headers['X-CSRF-Token']='invalid'
    assert client.post(f'/api/v1/admin/users/{row["id"]}/invitation',json={}).status_code==403
    client.headers['X-CSRF-Token']=csrf
    assert client.get('/api/v1/admin/staff-email-status').json()['enabled'] is False
