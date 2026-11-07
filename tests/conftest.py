import os
import tempfile
from pathlib import Path
import pytest

TEST_ROOT=Path(tempfile.mkdtemp(prefix='best5-api-tests-'))
os.environ.update(DATABASE_URL=f'sqlite:///{TEST_ROOT / "test.db"}', STORAGE_DIR=str(TEST_ROOT/'uploads'), LOG_DIR=str(TEST_ROOT/'logs'), BRANDING_PATH=str(TEST_ROOT/'branding'), INITIAL_ADMIN_EMAIL='admin@best5.co.za', INITIAL_ADMIN_PASSWORD='TestInitialPassword!2026', EMAIL_ENABLED='false', RATE_LIMIT_ENABLED='false')
from fastapi.testclient import TestClient
from src.main import app
from src.db.models import Base
from src.db.session import engine
import src.services.seed as seed_module
seed_module.ROOT=TEST_ROOT

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client


def login(client, email='admin@best5.co.za', password='TestInitialPassword!2026', change=True):
    result=client.post('/api/v1/auth/login',json={'email':email,'password':password,'remember':True})
    assert result.status_code==200,result.text
    csrf=client.cookies.get('best5_csrf')
    client.headers['X-CSRF-Token']=csrf
    if change:
        result=client.post('/api/v1/auth/change-password',json={'currentPassword':password,'newPassword':'ChangedTestPassword!2026'})
        assert result.status_code==200,result.text
    return result
