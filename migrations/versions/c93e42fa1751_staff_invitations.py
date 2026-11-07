"""Add expiring single-use staff setup invitations."""
from alembic import op
import sqlalchemy as sa
revision='c93e42fa1751'
down_revision='b82a31d9e640'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('staff_invitations',sa.Column('id',sa.String(64),primary_key=True),sa.Column('user_id',sa.String(36),nullable=False,unique=True),sa.Column('expires',sa.Float(),nullable=False),sa.Column('email_job_id',sa.String(36),nullable=False))

def downgrade():
    op.drop_table('staff_invitations')
