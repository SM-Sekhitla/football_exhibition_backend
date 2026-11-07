from uuid import uuid4
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from app.api.deps import DB, require
from app.core.config import settings
from app.core.security import hash_password, now, token
from app.db.models import Audit, EmailJob, Session, User
from app.schemas.auth import UserCreate, UserUpdate
from app.services.audit import audit
from app.services.content import lock_operations
from app.controllers.auth import public_user
from app.services.invitations import invite_staff, invitation_message, invitation_status, invalidate_invitations


def users(db: DB, user=Depends(require('users:manage'))):
    return [public_user(row) | {'active':row.active,'invitation':invitation_status(db,row)} for row in db.scalars(select(User).order_by(User.email))]


def create_user(body: UserCreate, db: DB, request: Request, user=Depends(require('users:manage'))):
    lock_operations(db)
    if db.scalar(select(User).where(User.email==str(body.email).lower())): raise HTTPException(409,'An account already exists for this email')
    row=User(id=str(uuid4()),email=str(body.email).lower(),name=body.name,password_hash=hash_password(body.password or token()),role=body.role,active=True,must_change_password=True)
    db.add(row); db.flush(); invite_staff(db,row)
    audit(db,'users','Staff account created; setup invitation queued',user.id,request.state.request_id); db.commit()
    return public_user(row) | {'active':row.active,'invitation':invitation_status(db,row),'message':invitation_message()}


def update_user(identifier: str, body: UserUpdate, db: DB, request: Request, user=Depends(require('users:manage'))):
    lock_operations(db)
    db.refresh(user)
    if not user.active or user.role != 'super_admin': raise HTTPException(403,'Only super admins can manage staff')
    if identifier==user.id: raise HTTPException(422,'You cannot deactivate or change your own role')
    row=db.get(User,identifier)
    if not row: raise HTTPException(404,'User not found')
    if row.role=='super_admin' and (body.role!='super_admin' or not body.active):
        count=db.scalar(select(func.count()).select_from(User).where(User.role=='super_admin',User.active.is_(True)))
        if row.active and count<=1: raise HTTPException(422,'Keep at least one active super admin')
    row.role=body.role; row.active=body.active
    if not row.active: invalidate_invitations(db,row.id)
    for session in db.scalars(select(Session).where(Session.user_id==identifier)): db.delete(session)
    audit(db,'users','Staff role or account status changed; sessions revoked',user.id,request.state.request_id); db.commit()
    return public_user(row) | {'active':row.active,'invitation':invitation_status(db,row)}


def logs(db: DB, category: str='', level: str='', page: int=Query(1,ge=1), limit: int=Query(50,ge=1,le=100), user=Depends(require('logs:read'))):
    query=select(Audit)
    if category: query=query.where(Audit.category==category)
    if level: query=query.where(Audit.level==level)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(Audit.created.desc()).offset((page-1)*limit).limit(limit))
    return {'items':[{'id':r.id,'createdAt':datetime.fromtimestamp(r.created,timezone.utc).isoformat(),'category':r.category,'level':r.level,'message':r.message,'actor':r.actor,'requestId':r.request_id} for r in rows], 'total':total,'page':page,'limit':limit}


def email_jobs(db: DB, user=Depends(require('logs:read'))):
    rows=db.scalars(select(EmailJob).order_by(EmailJob.next_attempt.desc()).limit(100))
    return {'enabled':settings.email_enabled,'items':[{'id':r.id,'subject':r.subject,'status':r.status,'attempts':r.attempts,'lastError':r.last_error,'providerId':r.provider_id} for r in rows]}


def retry_email(identifier: str, db: DB, request: Request, user=Depends(require('logs:read'))):
    if not settings.email_enabled: raise HTTPException(409,'Configure and enable Brevo email first')
    row=db.get(EmailJob,identifier)
    if not row or row.status not in ('failed','retry'): raise HTTPException(409,'Only failed or retrying emails can be retried')
    row.status='pending'; row.attempts=0; row.next_attempt=now()
    audit(db,'email','Email retry requested',user.id,request.state.request_id); db.commit()
    return {'message':'Email queued for retry'}


def request_logs(user=Depends(require('logs:read'))):
    import json
    from collections import deque
    path=settings.log_dir / 'backend.log'
    if not path.is_file(): return {'items':[]}
    with path.open() as file:
        lines=deque(file,maxlen=150)
    items=[]
    for line in reversed(lines):
        try: items.append(json.loads(line))
        except ValueError: continue
    return {'items':items}


def resend_invitation(identifier: str,db: DB,request: Request,user=Depends(require('users:manage'))):
    lock_operations(db)
    row=db.get(User,identifier)
    if not row or not row.active: raise HTTPException(404,'Active staff account not found')
    if row.id==user.id or not row.must_change_password: raise HTTPException(409,'This account already has a password. Use password recovery instead.')
    # Any previously shared temporary password and sessions stop working after resend.
    row.password_hash=hash_password(token())
    db.execute(delete(Session).where(Session.user_id==row.id))
    invite_staff(db,row)
    audit(db,'users','Staff setup invitation queued again; older links revoked',user.id,request.state.request_id); db.commit()
    return {'message':invitation_message(),'invitation':invitation_status(db,row)}


def staff_email_status(user=Depends(require('users:manage'))):
    return {'enabled':settings.email_enabled,'configured':bool(settings.brevo_api_key and settings.email_sender)}
