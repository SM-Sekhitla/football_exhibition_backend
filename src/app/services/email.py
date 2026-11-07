import asyncio
from uuid import uuid4
import httpx
from sqlalchemy import select, update
from app.core.config import settings
from app.core.security import now
from app.db.models import EmailJob
from app.db.session import SessionLocal
from app.services.audit import audit


def enqueue_email(db, recipient, subject, body, html_body=None):
    from app.services.email_templates import notification_email
    if html_body is None: html_body=notification_email(subject,body,db)
    job=EmailJob(id=str(uuid4()), recipient=recipient, subject=subject, body=body, html_body=html_body, status='pending', attempts=0, next_attempt=now())
    db.add(job)
    return job


def process_email_jobs():
    if not settings.email_enabled: return
    with SessionLocal() as db:
        abandoned=db.scalars(select(EmailJob).where(EmailJob.status=='sending',EmailJob.attempts>=5,EmailJob.next_attempt<=now())).all()
        for job in abandoned:
            job.status='failed'; job.last_error='Worker lease expired after final attempt'
            audit(db,'email',f'Email job exhausted retries; job {job.id}',level='WARNING')
        db.commit()
        jobs = db.scalars(select(EmailJob).where(EmailJob.status.in_(['pending','retry','sending']), EmailJob.next_attempt <= now(), EmailJob.attempts < 5).limit(10)).all()
        for job in jobs:
            from app.services.invitations import SUBJECT
            from app.db.models import StaffInvitation
            if job.subject==SUBJECT:
                invitation=db.scalar(select(StaffInvitation).where(StaffInvitation.email_job_id==job.id))
                if not invitation or invitation.expires<=now():
                    job.status='expired' if invitation else 'cancelled'; job.body=''; job.html_body=None; db.commit(); continue
            claimed = db.execute(update(EmailJob).where(EmailJob.id == job.id, EmailJob.status.in_(['pending','retry','sending']), EmailJob.next_attempt <= now()).values(status='sending', next_attempt=now()+120, attempts=EmailJob.attempts+1))
            db.commit()
            if not claimed.rowcount: continue
            db.refresh(job)
            try:
                from app.services.email_templates import notification_email
                html=job.html_body or notification_email(job.subject,job.body,db)
                response = httpx.post('https://api.brevo.com/v3/smtp/email', headers={'api-key': settings.brevo_api_key, 'accept': 'application/json'}, json={'sender': {'email': settings.email_sender, 'name': settings.email_sender_name}, 'to': [{'email': job.recipient}], 'subject': job.subject, 'textContent': job.body, 'htmlContent': html, 'headers': {'IdempotencyKey': job.id}}, timeout=20)
                response.raise_for_status()
                job.status = 'sent'; job.provider_id = response.json().get('messageId'); job.last_error = None
                # Reset tokens and message bodies are no longer retained once sent.
                job.body = ''; job.html_body=None
                audit(db, 'email', f'Email accepted by Brevo; job {job.id}')
            except httpx.HTTPError as exc:
                status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                job.last_error = f'Brevo HTTP {status}' if status else 'Brevo connection failed'
                retryable = status is None or status == 429 or status >= 500
                job.status = 'retry' if retryable and job.attempts < 5 else 'failed'
                job.next_attempt = now() + min(3600, 30 * 2 ** job.attempts)
                audit(db, 'email', f'{job.last_error}; job {job.id}; {job.status}', level='WARNING')
            db.commit()

async def email_worker(stop):
    while not stop.is_set():
        try: await asyncio.to_thread(process_email_jobs)
        except Exception:
            # Keep worker alive without logging payloads or provider responses.
            from app.core.logging import logger
            logger.error('Email worker iteration failed')
        try: await asyncio.wait_for(stop.wait(), timeout=10)
        except asyncio.TimeoutError: pass
