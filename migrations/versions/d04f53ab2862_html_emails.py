"""Store HTML email content alongside the plain-text fallback."""
from alembic import op
import sqlalchemy as sa
revision='d04f53ab2862'
down_revision='c93e42fa1751'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('email_jobs',sa.Column('html_body',sa.Text(),nullable=True))

def downgrade():
    op.drop_column('email_jobs','html_body')
