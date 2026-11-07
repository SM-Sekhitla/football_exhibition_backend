from alembic import context
from src.db.models import Base
from src.db.session import engine

if context.is_offline_mode():
    from src.core.config import settings
    context.configure(url=settings.database_url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=Base.metadata,render_as_batch=engine.dialect.name=='sqlite')
        with context.begin_transaction(): context.run_migrations()
