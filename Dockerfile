FROM python:3.12-slim
WORKDIR /app
COPY src/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src/app ./app
COPY src/alembic ./alembic
COPY src/alembic.ini ./
RUN useradd --create-home best5 && mkdir data logs && chown -R best5:best5 /app
USER best5
EXPOSE 8002
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host ${APP_HOST:-0.0.0.0} --port ${PORT:-${APP_PORT:-${BACKEND_PORT:-8002}}} --workers ${WEB_CONCURRENCY:-1} --no-proxy-headers"]
