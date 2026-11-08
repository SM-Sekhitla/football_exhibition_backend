from pathlib import Path
from typing import Annotated
import json
import re
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import AliasChoices, Field, field_validator, model_validator
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
CsvList = Annotated[list[str], NoDecode]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore', populate_by_name=True)
    environment: str = 'development'
    app_name: str = 'BEST5 API'
    docs_enabled: bool | None = None
    render_external_hostname: str = ''
    api_v1_prefix: str = '/api/v1'
    auto_create_tables: bool = True
    database_url: str = f'sqlite:///{ROOT / "data/best5.db"}'
    frontend_url: str = 'http://localhost:5173'
    cors_origins: CsvList = ['http://localhost:5173', 'http://127.0.0.1:5173']
    trusted_hosts: CsvList = ['localhost', '127.0.0.1', 'testserver']
    allowed_hosts: CsvList = []
    csrf_cookie_domain: str | None = None
    secure_cookies: bool = Field(False, validation_alias=AliasChoices('SECURE_COOKIES', 'COOKIE_SECURE'))
    session_hours: int = Field(12, gt=0)
    access_token_expire_minutes: int | None = Field(None, gt=0)
    remember_days: int = Field(7, gt=0, validation_alias=AliasChoices('REMEMBER_DAYS','REFRESH_TOKEN_EXPIRE_DAYS'))
    initial_admin_email: str = 'admin@best5.co.za'
    initial_admin_password: str = ''
    default_platform_admin_email: str = ''
    default_platform_admin_password: str = ''
    default_platform_admin_username: str = 'BEST5 Administrator'
    storage_dir: Path = Field(ROOT / 'data/uploads', validation_alias=AliasChoices('STORAGE_DIR','DOCUMENT_PATH'))
    branding_path: Path = ROOT / 'data/uploads'
    log_dir: Path = ROOT / 'logs'
    log_level: str = 'INFO'
    brevo_api_key: str = ''
    email_sender: str = ''
    email_sender_name: str = 'BEST5 Football Exhibition'
    email_logo_url: str = ''
    brevo_from_email: str = ''
    brevo_from_name: str = ''
    email_enabled: bool = False
    log_console: bool = True
    rate_limit_enabled: bool = True
    max_document_size_mb: int = Field(2, ge=1, le=50)
    max_branding_image_size_mb: int = Field(20, ge=1, le=50)
    allowed_document_types: CsvList = ['application/pdf','image/jpeg','image/png']
    allowed_branding_image_types: CsvList = ['image/jpeg','image/png','image/webp','image/gif','image/avif']

    @field_validator('cors_origins','trusted_hosts','allowed_hosts','allowed_document_types','allowed_branding_image_types',mode='before')
    @classmethod
    def lists(cls,value):
        if isinstance(value,str):
            return json.loads(value) if value.strip().startswith('[') else [part.strip() for part in value.split(',') if part.strip()]
        return value

    @field_validator('storage_dir','branding_path','log_dir',mode='after')
    @classmethod
    def paths(cls,value):
        return value if value.is_absolute() else ROOT / value

    @field_validator('api_v1_prefix')
    @classmethod
    def prefix(cls,value):
        value=value.rstrip('/')
        if not value.startswith('/') or value.startswith('//') or any(c in value for c in '?#{ }'):
            raise ValueError('API_V1_PREFIX must be an absolute URL path')
        return value

    @field_validator('csrf_cookie_domain',mode='before')
    @classmethod
    def cookie_domain(cls,value):
        if not value: return None
        value=value.strip().lstrip('.').lower()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',value):
            raise ValueError('CSRF_COOKIE_DOMAIN must be a hostname without scheme, path or port')
        return value

    @field_validator('log_level')
    @classmethod
    def level(cls,value):
        value=value.upper()
        if value not in ('DEBUG','INFO','WARNING','ERROR','CRITICAL'): raise ValueError('Invalid LOG_LEVEL')
        return value

    @field_validator('database_url')
    @classmethod
    def database_driver(cls,value):
        # PRISM uses asyncpg; this application's sessions are synchronous.
        url=make_url(value)
        if url.drivername in ('postgres','postgresql','postgresql+asyncpg'):
            url=url.set(drivername='postgresql+psycopg')
        return url.render_as_string(hide_password=False)

    @model_validator(mode='after')
    def configure(self):
        hosts=self.trusted_hosts+self.allowed_hosts
        if self.render_external_hostname:
            hostname=self.render_external_hostname.strip().lower()
            if len(hostname)>253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',hostname):
                raise ValueError('RENDER_EXTERNAL_HOSTNAME must be a hostname without scheme, port or wildcard')
            hosts=hosts+[hostname]
        self.trusted_hosts=list(dict.fromkeys(hosts))
        if not self.email_sender: self.email_sender=self.brevo_from_email
        if self.brevo_from_name and 'email_sender_name' not in self.model_fields_set:
            self.email_sender_name=self.brevo_from_name
        if self.default_platform_admin_email and 'initial_admin_email' not in self.model_fields_set:
            self.initial_admin_email=self.default_platform_admin_email
        if not self.initial_admin_password: self.initial_admin_password=self.default_platform_admin_password
        if self.environment == 'production':
            if not self.secure_cookies or not self.frontend_url.startswith('https://'):
                raise ValueError('Production requires secure cookies and an HTTPS frontend URL')
            if '*' in self.cors_origins or '*' in self.trusted_hosts:
                raise ValueError('Production requires explicit origins and hosts')
        if self.email_enabled and (not self.brevo_api_key or not self.email_sender):
            raise ValueError('Email requires BREVO_API_KEY and EMAIL_SENDER or BREVO_FROM_EMAIL')
        return self

    @property
    def session_seconds(self):
        return self.access_token_expire_minutes * 60 if self.access_token_expire_minutes is not None else self.session_hours * 3600

    @property
    def proof_types(self):
        # Registration POPs support these verified formats, not arbitrary office documents.
        return [mime for mime in self.allowed_document_types if mime in ('application/pdf','image/jpeg','image/png')]

    @property
    def image_types(self):
        return [mime for mime in self.allowed_branding_image_types if mime in ('image/jpeg','image/png','image/webp','image/gif','image/avif')]

settings = Settings()
