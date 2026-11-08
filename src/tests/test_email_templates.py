from html.parser import HTMLParser
import httpx
from sqlalchemy import select
from app.core.config import settings
from app.db.models import EmailJob
from app.db.session import SessionLocal
from app.services.email_templates import invitation_email,logo_url,password_reset_email
from app.services.email import process_email_jobs
from conftest import login

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.links.extend(value for key,value in attrs if key=='href')


def test_invitation_uses_site_colours_logo_button_and_escaped_recipient(monkeypatch):
    monkeypatch.setattr(settings,'email_logo_url','https://cdn.example.com/logo.png')
    link='https://best5.example/admin/accept-invitation#token=preview-only&source=email'
    html=invitation_email('<script>alert(1)</script>','super_admin',link)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'https://cdn.example.com/logo.png' in html and 'alt="BEST5"' in html
    assert '#07100c' in html and '#c8ff4b' in html and '#0d1d14' in html
    assert 'Create your password' in html and '48 hours' in html and 'Super Admin' in html
    assert 'role="presentation"' in html
    parser=Links();parser.feed(html)
    assert parser.links.count(link)==2


def test_logo_falls_back_to_site_and_unsafe_logo_schemes_are_ignored(monkeypatch):
    monkeypatch.setattr(settings,'email_logo_url','')
    assert logo_url()==settings.frontend_url.rstrip('/')+'/assets/images/logo/smt_logo.png'
    monkeypatch.setattr(settings,'email_logo_url','javascript:alert(1)')
    assert logo_url().startswith('http')


def test_password_reset_has_own_button_and_expiry():
    html=password_reset_email('https://best5.example/admin/reset-password?token=preview')
    assert 'Reset your password' in html and '30 minutes' in html


def test_brevo_receives_html_and_text_and_both_are_cleared_after_send(client,monkeypatch):
    login(client)
    response=client.post('/api/v1/admin/users',json={'email':'html-invite@example.com','name':'Email Guest','role':'editor'})
    assert response.status_code==201,response.text
    captured=[]
    def send(url,**kwargs):
        captured.append(kwargs['json'])
        return httpx.Response(201,json={'messageId':'html-message-id'},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',send)
    monkeypatch.setattr(settings,'email_enabled',True)
    process_email_jobs()
    assert len(captured)==1
    assert 'Create your password' in captured[0]['htmlContent']
    assert 'Choose your own password' in captured[0]['textContent']
    assert '<html' in captured[0]['htmlContent']
    with SessionLocal() as db:
        job=db.scalar(select(EmailJob).where(EmailJob.recipient=='html-invite@example.com'))
        assert job.status=='sent' and job.body=='' and job.html_body is None


def test_registration_receipt_has_reference_status_button_and_escaped_name(monkeypatch):
    from html import unescape
    from urllib.parse import urlsplit,parse_qs
    from app.services.email_templates import application_email
    monkeypatch.setattr(settings,'frontend_url','https://best5football.co.za')
    for kind in ('team','vendor'):
        text,html=application_email(kind,'United <script>bad()</script>','B5-REFERENCE')
        assert 'B5-REFERENCE' in text and 'B5-REFERENCE' in html
        assert 'Check application status' in html
        assert '<script>bad()' not in html
        assert '&lt;script&gt;' in html
        link=text.split('Check application status: ')[1].splitlines()[0]
        parsed=urlsplit(unescape(link))
        assert parsed.netloc=='best5football.co.za' and parsed.path=='/application-status'
        assert parse_qs(parsed.fragment)=={'reference':['B5-REFERENCE']}
