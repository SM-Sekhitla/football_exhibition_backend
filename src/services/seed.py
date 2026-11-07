import json
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from src.core.config import ROOT, settings
from src.core.security import hash_password, token
from src.db.models import Document, User
from src.services.audit import audit

DEFAULTS = json.loads(Path(__file__).with_name('defaults.json').read_text())

def seed(db):
    for key, value in DEFAULTS.items():
        if not db.get(Document, key): db.add(Document(key=key, value=value, revision=0))
    # Shared transaction locks/revisions for operations and applications.
    for key in ['teamRegs','vendorRegs','_operations']:
        if not db.get(Document,key): db.add(Document(key=key,value=[],revision=0))
    if not db.scalar(select(User).limit(1)):
        password = settings.initial_admin_password or token()[:24] + 'aA9!'
        if len(password) < 12: raise ValueError('INITIAL_ADMIN_PASSWORD must have at least 12 characters')
        user = User(id=str(uuid4()), email=settings.initial_admin_email.lower(), name=settings.default_platform_admin_username, password_hash=hash_password(password), role='super_admin', active=True, must_change_password=True)
        db.add(user)
        # Credentials are generated once, never printed into backend logs.
        target = ROOT / 'data/initial-admin.txt'
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write(f'Email: {user.email}\nPassword: {password}\nLogin: {settings.frontend_url}/admin/login\nChange this password on first sign-in. This file is not updated when the password changes.\n')
        audit(db, 'auth', 'Initial administrator created; first sign-in requires password change', user.id)
    from src.services.initial_admin import promote_initial_admin
    db.flush()
    promote_initial_admin(db)
    db.commit()
