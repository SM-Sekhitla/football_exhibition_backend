"""Promote the original bootstrap account to super admin without resetting credentials."""
from alembic import op
from sqlalchemy.orm import Session

revision='b82a31d9e640'
down_revision='695dfdedcffd'
branch_labels=None
depends_on=None

def upgrade():
    from app.services.initial_admin import promote_initial_admin
    with Session(bind=op.get_bind()) as db:
        promote_initial_admin(db)
        db.commit()

def downgrade():
    import sqlalchemy as sa
    bind=op.get_bind()
    marker=bind.execute(sa.text("SELECT value FROM documents WHERE key='_bootstrap_super_admin_v1'")).scalar()
    if marker:
        import json
        data=json.loads(marker) if isinstance(marker,str) else marker
        bind.execute(sa.text("UPDATE users SET role='admin' WHERE id=:id AND role='super_admin'"),{'id':data['userId']})
    bind.execute(sa.text("DELETE FROM documents WHERE key='_bootstrap_super_admin_v1'"))
