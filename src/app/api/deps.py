import secrets
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from app.db.session import get_db
from app.db.models import Session, User
from app.core.security import digest, now
from app.core.permissions import ROLES

DB = Annotated[DBSession, Depends(get_db)]

def current_user(request: Request, db: DB):
    raw = request.cookies.get('best5_session', '')
    session = db.get(Session, digest(raw)) if raw else None
    if not session or session.expires < now():
        raise HTTPException(401, 'Your session has expired. Please sign in.')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, 'Account unavailable')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf = request.headers.get('x-csrf-token', '')
        if not csrf or not secrets.compare_digest(digest(csrf), session.csrf_hash):
            raise HTTPException(403, 'Invalid CSRF token')
    request.state.user_id = user.id
    return user

CurrentUser = Annotated[User, Depends(current_user)]

def require(permission):
    def dependency(user: CurrentUser):
        if user.must_change_password:
            raise HTTPException(403, 'Change your initial password before continuing')
        if permission not in ROLES.get(user.role, set()):
            raise HTTPException(403, 'You do not have permission for this action')
        return user
    return dependency
