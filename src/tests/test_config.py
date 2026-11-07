from app.core.config import ROOT, Settings


def test_prism_style_configuration_is_applied_without_connecting(monkeypatch):
    monkeypatch.delenv('INITIAL_ADMIN_EMAIL',raising=False)
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD',raising=False)
    config = Settings(_env_file=None,
        database_url='postgresql+asyncpg://example:password@postgres:5432/best5',
        cors_origins='http://localhost:5174,http://127.0.0.1:5174',
        allowed_hosts='backend,localhost',
        storage_dir='storage/documents', branding_path='storage/branding',
        brevo_from_email='sender@example.com',brevo_from_name='Tournament',
        default_platform_admin_email='owner@example.com',default_platform_admin_password='InitialOwnerPassword!2026',
        access_token_expire_minutes=15,remember_days=14,
        auto_create_tables=False,app_name='Tournament API',api_v1_prefix='/api/v2/',log_level='warning')
    assert config.database_url.startswith('postgresql+psycopg://')
    assert config.cors_origins==['http://localhost:5174','http://127.0.0.1:5174']
    assert 'backend' in config.trusted_hosts
    assert config.storage_dir==ROOT/'storage/documents' and config.branding_path==ROOT/'storage/branding'
    assert config.email_sender=='sender@example.com' and config.email_sender_name=='Tournament'
    assert config.initial_admin_email=='owner@example.com'
    assert config.initial_admin_password=='InitialOwnerPassword!2026'
    assert config.session_seconds==900 and config.remember_days==14
    assert config.api_v1_prefix=='/api/v2' and config.log_level=='WARNING'
    assert not config.auto_create_tables


def test_canonical_names_override_aliases():
    config=Settings(_env_file=None, email_sender='primary@example.com',brevo_from_email='alias@example.com',
        email_sender_name='Primary',brevo_from_name='Alias',initial_admin_email='primary@example.com',
        default_platform_admin_email='alias@example.com',initial_admin_password='PrimaryPassword!2026',
        default_platform_admin_password='AliasPassword!2026')
    assert config.email_sender=='primary@example.com' and config.email_sender_name=='Primary'
    assert config.initial_admin_email=='primary@example.com' and config.initial_admin_password=='PrimaryPassword!2026'


def test_last_dotenv_assignment_wins_and_limits_are_configured(tmp_path):
    env=tmp_path/'.env'
    env.write_text('BREVO_API_KEY=earlier-value\nBREVO_API_KEY=\nMAX_DOCUMENT_SIZE_MB=25\nMAX_BRANDING_IMAGE_SIZE_MB=5\nALLOWED_DOCUMENT_TYPES=application/pdf,application/msword,image/png\n')
    config=Settings(_env_file=env)
    assert config.brevo_api_key==''
    assert config.max_document_size_mb==25 and config.max_branding_image_size_mb==5
    assert config.proof_types==['application/pdf','image/png']


def test_render_hostname_is_added_without_trusting_other_domains(monkeypatch):
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME','football-exhibition-backend.onrender.com')
    config=Settings(_env_file=None, trusted_hosts=['localhost'], allowed_hosts=['custom.example.com'])
    assert config.trusted_hosts==['localhost','custom.example.com','football-exhibition-backend.onrender.com']
    assert '*' not in config.trusted_hosts


def test_render_hostname_rejects_urls_and_wildcards():
    import pytest
    for value in ['https://example.com','*.onrender.com','example.com/path','example.com:443']:
        with pytest.raises(ValueError):
            Settings(_env_file=None,render_external_hostname=value)


def test_docs_can_be_enabled_in_production():
    config=Settings(_env_file=None,environment='production',secure_cookies=True,
        frontend_url='https://example.com',docs_enabled=True)
    assert config.docs_enabled is True


def test_docs_accept_configured_host_and_reject_unknown_host(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app, settings
    monkeypatch.setattr(settings,'trusted_hosts',['football-exhibition-backend.onrender.com'])
    monkeypatch.setattr(settings,'docs_enabled',True)
    client=TestClient(create_app(),base_url='https://football-exhibition-backend.onrender.com')
    assert client.get('/docs').status_code==200
    assert client.get('/docs',headers={'host':'untrusted.example.com'}).status_code==400
