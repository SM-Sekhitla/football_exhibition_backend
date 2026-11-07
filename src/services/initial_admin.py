"""One-time promotion of the original bootstrap account, preserving its password."""
from sqlalchemy import select
from src.core.config import settings
from src.db.models import Audit, Document, User
from src.services.audit import audit

MARKER = '_bootstrap_super_admin_v1'

def promote_initial_admin(db):
    if db.get(Document,MARKER): return
    first_actor = db.scalar(select(Audit.actor).where(Audit.category=='auth',Audit.message=='Initial administrator created; first sign-in requires password change').order_by(Audit.created).limit(1))
    user = db.get(User,first_actor) if first_actor else db.scalar(select(User).where(User.email==settings.initial_admin_email.lower()))
    if not user: return
    if user.role != 'super_admin':
        user.role='super_admin'
        audit(db,'users','Initial administrator promoted to super admin',user.id)
    db.add(Document(key=MARKER,value={'userId':user.id},revision=0))
