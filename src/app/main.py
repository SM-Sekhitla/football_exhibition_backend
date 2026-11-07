import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.api.v1.router import router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import Base
from app.db.session import engine, SessionLocal
from app.middleware.security import SecurityMiddleware
from app.services.seed import seed
from app.services.email import email_worker

@asynccontextmanager
async def lifespan(app):
    configure_logging()
    if settings.auto_create_tables and settings.environment != 'production': Base.metadata.create_all(engine)
    with SessionLocal() as db: seed(db)
    stop=asyncio.Event(); task=asyncio.create_task(email_worker(stop))
    yield
    stop.set(); await task


def create_app():
    app=FastAPI(title=settings.app_name,version='1.0.0',lifespan=lifespan,docs_url='/docs' if (settings.docs_enabled if settings.docs_enabled is not None else settings.environment!='production') else None,redoc_url=None)
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=settings.trusted_hosts)
    app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','X-CSRF-Token','X-Request-ID'],expose_headers=['X-Request-ID'])
    @app.exception_handler(RequestValidationError)
    async def validation(request: Request,exc):
        # Pydantic errors normally echo input values, which can include passwords/POPs.
        return JSONResponse({'detail':'; '.join(f'{".".join(str(x) for x in e["loc"])}: {e["msg"]}' for e in exc.errors())},422)
    @app.exception_handler(IntegrityError)
    async def integrity(request: Request,exc):
        return JSONResponse({'detail':'A matching record already exists. Refresh and try again.'},409)
    app.include_router(router,prefix=settings.api_v1_prefix)
    return app

app=create_app()
