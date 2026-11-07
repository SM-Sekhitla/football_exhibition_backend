"""Read-only connection check with actionable, credential-free diagnostics."""
import sys
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.db.session import engine


def main():
    url=make_url(settings.database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except SQLAlchemyError:
        print(f'Database connection failed ({url.get_backend_name()}, host={url.host or "local"}, port={url.port or "default"}).',file=sys.stderr)
        if url.get_backend_name()=='postgresql':
            print('For local development, run: docker compose up -d postgres',file=sys.stderr)
            print('Use the published host/port in DATABASE_URL (local default: 127.0.0.1:5434). Docker service names such as postgres only resolve on their Docker network.',file=sys.stderr)
            print('If the database is running, check the database name and credentials in .env.',file=sys.stderr)
        return 1
    print('Database connection OK.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
