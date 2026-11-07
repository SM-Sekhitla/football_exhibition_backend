from datetime import timedelta
from uuid import uuid4
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, select
from app.api.deps import DB, CurrentUser
from app.core.config import settings
from app.core.permissions import ROLES
from app.core.security import DUMMY_HASH, digest, hash_password, now, token, verify_password
from app.db.models import PasswordReset, Session, StaffInvitation, User
from app.schemas.auth import ChangePassword, Login, ResetPassword, ResetRequest
from app.services.audit import audit
from app.services.email import enqueue_email
from app.services.email_templates import password_reset_email
from app.services.invitations import invalidate_invitations
from app.services.content import lock_operations

COOKIE = dict(httponly=True, secure=settings.secure_cookies, samesite='lax', path=settings.api_v1_prefix)

def public_user(user):
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'permissions': sorted(ROLES.get(user.role, set())), 'mustChangePassword': user.must_change_password}

def login(body: Login, request: Request, response: Response, db: DB):
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.active:
        audit(db, 'auth', 'Sign-in failed', request_id=request.state.request_id, level='WARNING'); db.commit()
        raise HTTPException(401, 'Incorrect email or password')
    raw, csrf = token(), token()
    duration = int(timedelta(days=settings.remember_days).total_seconds() if body.remember else settings.session_seconds)
    old = request.cookies.get('best5_session')
    if old: db.execute(delete(Session).where(Session.id == digest(old)))
    db.add(Session(id=digest(raw), user_id=user.id, csrf_hash=digest(csrf), expires=now() + duration))
    audit(db, 'auth', 'Signed in', user.id, request.state.request_id); db.commit()
    response.set_cookie('best5_session', raw, max_age=duration if body.remember else None, **COOKIE)
    response.set_cookie('best5_csrf', csrf, max_age=duration if body.remember else None, httponly=False, secure=settings.secure_cookies, samesite='lax', path='/')
    return public_user(user)

def me(user: CurrentUser):
    return public_user(user)

def logout(request: Request, response: Response, db: DB, user: CurrentUser):
    db.execute(delete(Session).where(Session.id == digest(request.cookies.get('best5_session', ''))))
    audit(db, 'auth', 'Signed out', user.id, request.state.request_id); db.commit()
    response.delete_cookie('best5_session', path=settings.api_v1_prefix, secure=settings.secure_cookies, httponly=True, samesite='lax')
    response.delete_cookie('best5_csrf', path='/')
    return {'message': 'Signed out'}

def change_password(body: ChangePassword, db: DB, user: CurrentUser, request: Request):
    lock_operations(db)
    db.refresh(user)
    if not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(403, 'Current password is incorrect')
    if body.currentPassword == body.newPassword:
        raise HTTPException(422, 'Choose a different password')
    user.password_hash = hash_password(body.newPassword); user.must_change_password = False
    current = digest(request.cookies.get('best5_session', ''))
    db.execute(delete(Session).where(Session.user_id == user.id, Session.id != current))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    invalidate_invitations(db,user.id)
    audit(db, 'auth', 'Password changed; other sessions revoked', user.id, request.state.request_id); db.commit()
    return public_user(user)

def forgot_password(body: ResetRequest, db: DB):
    user = db.scalar(select(User).where(User.email == str(body.email).lower(), User.active.is_(True)))
    if user:
        raw = token()
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.add(PasswordReset(id=digest(raw), user_id=user.id, expires=now() + 1800))
        link=f'{settings.frontend_url}/admin/reset-password?token={raw}'
        enqueue_email(db,user.email,'Reset your BEST5 password',f'Reset your password within 30 minutes: {link}',html_body=password_reset_email(link,db))
        db.commit()
    return {'message': 'If an active account matches, a reset email will be sent.'}

def reset_password(body: ResetPassword, db: DB):
    lock_operations(db)
    row = db.get(PasswordReset, digest(body.token))
    if not row or row.expires < now(): raise HTTPException(400, 'Invalid or expired reset link')
    user = db.get(User, row.user_id)
    if not user or not user.active: raise HTTPException(400, 'Invalid or expired reset link')
    # Conditional deletion makes concurrent attempts unable to reuse the token.
    result = db.execute(delete(PasswordReset).where(PasswordReset.id == row.id))
    if result.rowcount != 1: raise HTTPException(400, 'Reset link already used')
    user.password_hash = hash_password(body.password); user.must_change_password = False
    db.execute(delete(Session).where(Session.user_id == user.id))
    invalidate_invitations(db,user.id)
    audit(db, 'auth', 'Password reset; all sessions revoked', user.id); db.commit()
    return {'message': 'Password reset. Sign in with your new password.'}


def accept_invitation(body: ResetPassword,db: DB):
    lock_operations(db)
    invitation=db.get(StaffInvitation,digest(body.token))
    if not invitation or invitation.expires<=now(): raise HTTPException(400,'This invitation is invalid or expired. Ask your super admin for a new invitation.')
    user=db.get(User,invitation.user_id)
    if not user or not user.active or not user.must_change_password: raise HTTPException(400,'This invitation is no longer available.')
    user.password_hash=hash_password(body.password); user.must_change_password=False
    invalidate_invitations(db,user.id)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id==user.id))
    db.execute(delete(Session).where(Session.user_id==user.id))
    audit(db,'auth','Staff invitation accepted; password set',user.id); db.commit()
    return {'message':'Your password has been set. You can now sign in with your email address and new password.'}
