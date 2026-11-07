"""Start an isolated backend for Playwright. Never reads/writes the development DB."""
import os
import sys
import tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
database=Path(os.environ['BEST5_E2E_DB_PATH']) if os.environ.get('BEST5_E2E_DB_PATH') else Path(tempfile.mkdtemp(prefix='best5-browser-tests-'))/'e2e.db'
data=database.parent
data.mkdir(parents=True,exist_ok=True)
os.environ.update(DATABASE_URL=f'sqlite:///{database}',STORAGE_DIR=str(data/'uploads'),LOG_DIR=str(data/'logs'),BRANDING_PATH=str(data/'branding'),AUTO_CREATE_TABLES='true',INITIAL_ADMIN_EMAIL='admin@best5.co.za',INITIAL_ADMIN_PASSWORD='BrowserInitialPassword!2026',EMAIL_ENABLED='false',LOG_CONSOLE='false',RATE_LIMIT_ENABLED='false',CORS_ORIGINS='["http://127.0.0.1:5175"]')
import src.services.seed as seed_module
seed_module.ROOT=data
import uvicorn
uvicorn.run('src.main:app',host='127.0.0.1',port=8001,proxy_headers=False,log_level='warning')
