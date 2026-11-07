from urllib.parse import urlencode
from sqlalchemy import delete, select
from src.core.config import settings
from src.core.security import digest, now, token
from src.db.models import EmailJob, StaffInvitation
from src.services.email import enqueue_email
from src.services.email_templates import invitation_email

SUBJECT='Set up your BEST5 staff account'


def invalidate_invitations(db,user_id):
    for invitation in db.scalars(select(StaffInvitation).where(StaffInvitation.user_id==user_id)).all():
        job=db.get(EmailJob,invitation.email_job_id)
        if job and job.status in ('pending','retry','sending'):
            job.status='cancelled'; job.body=''; job.html_body=None
    db.execute(delete(StaffInvitation).where(StaffInvitation.user_id==user_id))


def invite_staff(db,user):
    invalidate_invitations(db,user.id)
    raw=token(); expires=now()+48*3600
    link=f'{settings.frontend_url.rstrip("/")}/admin/accept-invitation#{urlencode({"token":raw})}'
    job=enqueue_email(db,user.email,SUBJECT,f'Hello {user.name},\n\nYou have been invited to BEST5 as {user.role.replace("_"," ")}.\n\nChoose your own password using this link within 48 hours:\n{link}\n\nAfter setting your password, sign in at {settings.frontend_url.rstrip("/")}/admin/login with this email address.\n\nNo temporary password is required. If you were not expecting this invitation, contact the organiser.',html_body=invitation_email(user.name,user.role,link,db))
    invitation=StaffInvitation(id=digest(raw),user_id=user.id,expires=expires,email_job_id=job.id)
    db.add(invitation)
    return invitation


def invitation_status(db,user):
    if not user.must_change_password: return {'status':'Accepted','emailStatus':None,'expiresAt':None}
    invitation=db.scalar(select(StaffInvitation).where(StaffInvitation.user_id==user.id))
    if not invitation: return {'status':'Not invited','emailStatus':None,'expiresAt':None}
    from datetime import datetime,timezone
    job=db.get(EmailJob,invitation.email_job_id)
    return {'status':'Expired' if invitation.expires<now() else 'Pending','emailStatus':job.status if job else 'unavailable','expiresAt':datetime.fromtimestamp(invitation.expires,timezone.utc).isoformat()}


def invitation_message():
    return 'Invitation queued. The user will receive a link to choose their password.' if settings.email_enabled else 'Account ready; invitation queued, but email delivery is disabled. Enable Brevo delivery, then send a fresh invitation.'
