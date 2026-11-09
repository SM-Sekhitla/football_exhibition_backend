# BEST5 backend

FastAPI backend for `../football_exhibition_cms`, following PRISM's separation of versioned routes, controllers, services, schemas, database models, dependencies, and middleware. Application code lives under `src/app/`; runtime configuration, migrations, scripts, tests and local storage live under `src/`. This is a single-tournament application; PRISM's tenant-specific CRM logic is intentionally not copied.

## Run locally

From this directory, run:

```bash
python3 src/run_backend.py
```

The launcher creates `src/.venv` if needed, installs the pinned dependencies, checks the configured database, applies Alembic migrations, and starts `app.main:app` with automatic reload. It checks `/api/v1/health` before reporting readiness. The Brevo worker already runs inside the API; no separate worker is started. Ctrl+C stops the server and reload children.

Create `src/.env` from `src/.env.example` to customise configuration. Existing `src/.env` files and credentials are preserved. The launcher checks for an occupied port before installing dependencies or applying migrations.

```bash
python3 src/run_backend.py --skip-install             # Faster subsequent starts
python3 src/run_backend.py --no-reload                # Disable reload
python3 src/run_backend.py --port 8012                # Custom local port
```

Port precedence is `--port`, then `APP_PORT`, `BACKEND_PORT`, `BEST5_PORT`, then `8002`. Host precedence is `--host`, `APP_HOST`, then `127.0.0.1`. Values can come from the shell environment or `src/.env` (the shell wins for each key). When changing ports, update the frontend's `BEST5_BACKEND_URL` accordingly. The existing `./src/scripts/start.sh` remains available for starting an already-installed environment without reload.

Port 8000 was already occupied locally, so this project defaults to 8002 (`BEST5_PORT` overrides the startup port). The API listens at `http://127.0.0.1:8002`, with development documentation at `/docs` and health at `/api/v1/health`. Start the frontend in a second terminal:

```bash
cd ../football_exhibition_cms
npm install
npm run dev
```

Vite forwards `/api` to port 8002. Use the same hostname throughout (`localhost` or `127.0.0.1`) so session and CSRF cookies remain consistent. The frontend waits for API bootstrap and shows a retry action if unavailable. Form drafts remain local; shared content, registrations, uploaded files, and authentication do not use browser local storage. Public data refreshes every 30 seconds for signed-out visitors while the page is visible and on returning to the tab. Admin snapshots refresh on page loads and successful mutations so an open editor retains its starting revision.

## Local PostgreSQL

The local backend runs on your computer, so its database URL must use a published host address. `postgres` is a Docker network service name and does not resolve in a host Python process.

A dedicated BEST5 database is defined in `docker-compose.yml`, isolated from the PRISM and other project containers:

```bash
docker compose --env-file src/.env up -d postgres
python3 src/run_backend.py --skip-install
```

The database is published at `127.0.0.1:5434` (`POSTGRES_PORT` overrides this mapping). The backend `src/.env` uses this address and retains its configured database credentials. If changing `POSTGRES_PORT`, update the port in `DATABASE_URL` too. Data persists in the `best5-local_postgres_data` Docker volume. Stop it with `docker compose --env-file src/.env stop postgres`; do not remove the volume when you want to preserve data.

The frontend's native-development proxy uses `http://127.0.0.1:8002`. For a backend running inside the same Compose network instead, use the service address `postgres:5432` for its database connection. A separate database does not import data from other projects or the old SQLite file.

## Environment configuration

The backend loads `src/.env`; the frontend loads its own root `.env`. Shell variables override file values; the final occurrence of a repeated key in a file wins, including an empty assignment. Existing `src/.env` files are not rewritten by this integration.

The current frontend configuration selects port **5174**, origin `http://localhost:5174`, and API target `http://127.0.0.1:8002`. The current backend configuration selects port **8002**, PostgreSQL at `127.0.0.1:5434`, and CORS origins on port **5174**. The native-development URLs use published loopback addresses. Docker-only service names should be used only by processes on the corresponding Docker network; the code does not silently substitute another database or API server.

| Setting | Used by |
| --- | --- |
| `FRONTEND_PORT` | Vite development/preview port, with strict port selection |
| `VITE_API_URL` | Browser API path and local proxy path |
| `VITE_API_TARGET` | Vite API proxy destination; legacy `BEST5_BACKEND_URL` is supported |
| `VITE_FRONTEND_BASE_URL` | Vite development origin and fallback frontend port |
| `VITE_ALLOWED_HOSTS` | Vite hostname allowlist (CSV or JSON list) |
| `VITE_GIT_VERSION` | Build version stored on the document root for diagnostics |
| `APP_HOST`, `APP_PORT`, `BACKEND_PORT`, `BEST5_PORT` | Local backend launcher bind address and port |
| `WEB_CONCURRENCY` | Worker count when reload is disabled |
| `APP_NAME`, `API_V1_PREFIX`, `AUTO_CREATE_TABLES` | API title, route prefix and development table creation |
| `DATABASE_URL` | SQLAlchemy sessions and Alembic migrations |
| `CORS_ORIGINS`, `TRUSTED_HOSTS`, `ALLOWED_HOSTS` | CORS and hostname checks; host lists combine |
| `SECURE_COOKIES` / `COOKIE_SECURE` | Secure cookie flag (canonical setting wins) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session expiry in minutes, overriding the default `SESSION_HOURS` |
| `REMEMBER_DAYS` / `REFRESH_TOKEN_EXPIRE_DAYS` | Remember-me session duration |
| `EMAIL_SENDER` / `BREVO_FROM_EMAIL` | Brevo sender (nonempty canonical setting wins) |
| `EMAIL_SENDER_NAME` / `BREVO_FROM_NAME` | Brevo display name (explicit canonical setting wins) |
| `INITIAL_ADMIN_*` / `DEFAULT_PLATFORM_ADMIN_*` | Initial account creation only; existing accounts are not reset |
| `DOCUMENT_PATH` / `STORAGE_DIR`, `BRANDING_PATH` | Private proof and public image storage paths; legacy uploads remain readable |
| `MAX_DOCUMENT_SIZE_MB`, `MAX_BRANDING_IMAGE_SIZE_MB` | Upload limits, also supplied to the frontend |
| `ALLOWED_DOCUMENT_TYPES`, `ALLOWED_BRANDING_IMAGE_TYPES` | Upload allowlists; POPs remain limited to verified PDF/JPEG/PNG formats |
| `LOG_DIR`, `LOG_LEVEL` | Backend log path and level |

`postgresql+asyncpg://` URLs from the PRISM configuration are adapted to `postgresql+psycopg://` because this backend uses synchronous sessions. Host, database, username and password are preserved. With `AUTO_CREATE_TABLES=false`, run migrations through the launcher before using the API.

This backend continues to use opaque server-side sessions and Brevo transactional email. Copied CRM variables for JWT signing (`SECRET_KEY`, `REFRESH_SECRET_KEY`, `TOKEN_ISSUER`), bootstrap secrets, SMTP/Mailpit, pgAdmin and PostgreSQL container creation do not change those authentication/email flows or launch infrastructure. `POSTGRES_*` variables configure a PostgreSQL container when used by your infrastructure; `DATABASE_URL` determines this application's connection. Brevo delivery requires `EMAIL_ENABLED=true` and a nonempty API key and sender. A later blank `BREVO_API_KEY=` disables use of an earlier key rather than restoring it.

## Initial administrator

The first startup creates `admin@best5.co.za` with the `super_admin` role. A random password is saved once in **`data/initial-admin.txt`**, readable only by the local owner and excluded from Git. The initial administrator has already been created in the local development database. Migration `b82a31d9e640` promotes the original bootstrap account once, preserving its password and leaving other admins unchanged. Open `/admin/login` and use the credentials in that file. You must replace the password at first sign-in. Subsequent restarts preserve the account and do not reset its password.

For a new database, `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` can override the generated credentials; passwords must have at least 12 characters. Do not commit credentials. The generated credential file is not updated when passwords change; remove it after your first successful password change.

## Layout

```text
README.md
docker-compose.yml    Local PostgreSQL service; use --env-file src/.env
Dockerfile            Deployment image built from the repository root
src/
  app/                Python application package
    api/              Versioned routes and authentication dependencies
    controllers/      HTTP endpoints
    core/             Configuration, security, RBAC and logging
    db/               Models and sessions
    middleware/       Request validation, limits and security headers
    schemas/          Request validation
    services/         Workflows, uploads, audit and Brevo outbox
  alembic/            Schema migration history
  scripts/            Startup, email preview and browser-test helpers
  tests/              Backend tests
  data/               Local data and bootstrap credentials (ignored)
  logs/               Runtime logs (ignored)
  storage/            Uploaded files (ignored)
  .venv/              Local Python environment (ignored)
  .env                Local configuration and secrets (ignored)
  .env.example
  alembic.ini
  pytest.ini
  requirements.txt
  run_backend.py
```

My Account is under `Settings → My Account`; it is available to every signed-in staff role. Password setup, change and reset fields provide independent show/hide controls.

## Auth and roles

The server stores only SHA-256 hashes of random session tokens; the browser receives an HttpOnly session cookie. Sessions expire after 12 hours, or 7 days for Remember me, configurable through environment settings. Unsafe authenticated requests require a session-bound `X-CSRF-Token`; the frontend reads the matching CSRF cookie. Logout revokes the session in the database. Password changes revoke other sessions; password resets revoke all sessions and use single-use 30-minute tokens. The initial bootstrap account must replace its temporary password on first login. New staff receive a single-use setup invitation and choose their own password before signing in.

| Role | Access |
| --- | --- |
| super_admin | All administration, including staff, roles and backend/email logs |
| admin | Content, tournament operations, settings and banking; no staff or backend logs |
| manager | Content and tournament operations; settings read |
| editor | Content management |
| reviewer | Applications, teams and fixtures |

`Settings → Staff & Roles` is available only to super admins and manages accounts of all roles and deactivation. Users cannot alter their own role or deactivate themselves. Role changes revoke the affected staff member's sessions. Permissions are enforced by API dependencies, not just navigation visibility.

Banking changes are accepted only through the dedicated `/admin/settings/banking` endpoint, which verifies the signed-in administrator's current password for every save. Generic settings saves cannot bypass this check. Audit entries record the actor and request ID without storing the supplied password or bank account values.

## Staff email invitations

Use `Settings → Staff & Roles → Create & invite user`. Enter the staff member's name, email and role; no administrator-chosen password is required. Account creation and the invitation email are saved in one database transaction. The recipient opens `/admin/accept-invitation#token=...`, chooses and confirms a password of at least 12 characters, then signs in normally with their assigned role.

Invitation tokens are stored hashed, expire after 48 hours, and can be used only once. They are separate from password-reset tokens. An accepted invitation clears the initial-password-change requirement. Resending invalidates all earlier invitation links and any previously shared temporary password; deactivation invalidates outstanding invitations. Completed accounts use normal password recovery instead.

For staff created before this feature, use **Send setup email** on their pending account. For a failed/expired invitation, use **Resend invitation**, which generates a fresh link. Account cards show setup and email queue status; **Refresh staff** reloads it. `sent` means Brevo accepted the message, not confirmed inbox delivery.

Delivery requires `EMAIL_ENABLED=true`, a valid `BREVO_API_KEY` and a verified `EMAIL_SENDER` (or `BREVO_FROM_EMAIL`). Restart the backend after changing `src/.env`. When email is disabled, creation explicitly reports that the invitation is queued but cannot be delivered. The application never displays a token/link in admin API responses or request/audit logs. Expired invitation emails are not sent; request a new invitation instead.

## Registrations and files

- Team submissions validate prerequisites acknowledgement, 5–8 distinct players, required fields and a PDF/JPG/PNG POP up to the configured document limit. Submitted status, reference, timestamps, approval and payment state are assigned by the server.
- PDF header/trailer and image content are checked. Private POPs are saved outside public static hosting and require an operations permission to download. Public application lookup returns only the application name, approval, payment state and review note.
- Team names and business names have case-insensitive application uniqueness. A duplicate/rejected application currently requires organiser assistance; applicant correction/resubmission is not implemented.
- Approval requires verified payment and creates the official team atomically. Capacity checks and promotions share a database lock/revision so concurrent approvals cannot fill the same final place. Reversing approval removes the official team unless fixtures reference it.
- Public content is filtered: drafts, hidden vendors/gallery entries, application details and private media are excluded. Admin snapshots expose application lists only to operations roles.
- Content saves carry a revision. Stale edits return HTTP 409 instead of overwriting another administrator's work. HTML is sanitised on the server and again when rendered by the frontend.
- Teams start empty. Startup never deletes existing backend teams, fixtures or registrations. Old preview browser data is not automatically imported.

## Brevo email

Set these in `src/.env` and restart the backend:

```dotenv
BREVO_API_KEY=your-brevo-api-key
EMAIL_SENDER=your-verified-sender@example.com
EMAIL_SENDER_NAME=BEST5 Football Exhibition
EMAIL_ENABLED=true
```

`EMAIL_SENDER` must be verified in your Brevo account. The integration uses Brevo's transactional `POST /v3/smtp/email` API and `api-key` header, as documented at https://developers.brevo.com/reference/send-transac-email.

Registration receipts, staff setup invitations, application/payment updates, and password-reset emails are queued in the database within their business transaction. A background worker claims jobs using a recoverable lease, sends through Brevo, and retries transient network, rate-limit and provider failures with backoff (up to five attempts). Jobs use a stable idempotency key. Email failure never discards a saved registration. A provider success means Brevo accepted the email; final inbox delivery/bounces require a webhook integration, which is not included.

Email is disabled by default. Queued emails remain pending until configured; no live email was sent during development or tests. Reset links expire after 30 minutes even if delivery is delayed. Backend requests and audit logs never contain request bodies, credentials, POP contents, reset tokens or Brevo API keys.

## Branded email design

Invitation emails use the site's forest-green and lime colours, BEST5 logo, a clear Create your password button, role details and a 48-hour expiry note. Password resets and other notifications use the same responsive table-based layout with inline styles. Brevo receives both `htmlContent` and `textContent`, and both stored bodies are removed after successful sending or invitation cancellation.

The logo defaults to the main logo saved in site branding. Set `EMAIL_LOGO_URL` to a publicly accessible HTTPS image URL (for example, a Brevo image-library URL) if the site is still running on localhost. Localhost image URLs are not reachable by recipients' email image proxies. The text BEST5 wordmark remains readable when images are blocked. Email action links also use `FRONTEND_URL`; use your public site URL when inviting people on other devices.

Preview without sending email:

```bash
src/.venv/bin/python src/scripts/preview_email.py
```

This writes `/tmp/best5-invitation-preview.html` with the local logo embedded for offline preview and a nonfunctional demonstration token. Invitations already delivered remain unchanged; use Resend invitation to generate a new message with the updated design.

## Logs

`Admin → Backend Logs` provides paginated/filterable audit records, recent backend request logs, email job status and explicit retry for failed/retrying jobs. Backend log and email-job access is super-admin-only. Request logs include request IDs, path (without query parameters), status and duration. Rotating JSON logs are stored at `logs/backend.log`; the database retains business audit history.

## Database and deployment

SQLite is the zero-configuration local default. PostgreSQL is supported using:

```dotenv
DATABASE_URL=postgresql+psycopg://best5:password@localhost:5432/best5
```

Run `cd src && .venv/bin/alembic upgrade head` before production startup. Development can create missing tables; production requires migrations. Keep the database, configured `DOCUMENT_PATH`/`BRANDING_PATH` upload directories (or legacy `data/uploads`), and logs on persistent storage and back up the database and uploads together. Uploaded assets cannot be recovered from the database alone.

For production, set `ENVIRONMENT=production`, `SECURE_COOKIES=true`, `FRONTEND_URL=https://your-domain`, explicit `CORS_ORIGINS`, and `TRUSTED_HOSTS`. HTTPS and secure cookies are enforced by startup configuration. Serve the frontend and `/api` through the same HTTPS origin so the browser can send cookies and the CSRF header. Never expose `data/`, the initial credential file, or logs as static files.

The built-in rate limiter is per process and uses the actual connecting IP, ignoring untrusted forwarded headers. Put a trusted ingress with shared rate limits in front of multiple workers/replicas. Use PostgreSQL and shared/persistent upload storage for multi-instance deployment; do not deploy separate local SQLite files across replicas. No cloud deployment, domain/TLS setup or Brevo account configuration is performed automatically.

## Tests

```bash
cd src && .venv/bin/python -m pytest -q
cd ../football_exhibition_cms
npm run typecheck
npm run lint
npm run build
npx playwright test --project=chromium
```

API tests cover authentication, forced password changes, CSRF, RBAC, private uploads, registration lookup, banking bypass prevention, optimistic revisions, sanitisation, reset-token reuse, Brevo retries, and concurrent capacity enforcement. Browser tests launch an isolated temporary backend database on port 8001 and frontend on 5175; they never use the development database, initial admin account or live email credentials.

Build the backend image from the repository root: `docker build -t best5-backend .`. For deployment, use Dockerfile path `./Dockerfile` and build context `.`. The container uses the hosting provider’s `PORT` when set, then `APP_PORT`, `BACKEND_PORT`, or 8002. Configure backend secrets through the hosting environment; local `.env` files are excluded from the image. Run Compose from the repository root with `--env-file src/.env` to load the backend configuration.

## Render host validation and API docs

The API adds Render's `RENDER_EXTERNAL_HOSTNAME` to its explicit host allowlist automatically. Add custom domains through `ALLOWED_HOSTS` (hostnames only, no `https://` or paths). For existing deployments before this change, set `ALLOWED_HOSTS=football-exhibition-backend.onrender.com` and redeploy to resolve `Invalid host header`.

Swagger is at `/docs` in development. To enable it in production, set `DOCS_ENABLED=true` in the service environment and redeploy. Set the health-check path to `/api/v1/health`; `/` is not an application endpoint.

## Persistent uploads on Sivehost

Set `UPLOAD_STORAGE=ftps` and configure the restricted Sivehost account in Render to store new images and POP files outside Render's temporary filesystem. The existing download URLs and permissions are retained. See [Sivehost storage setup](src/docs/sivehost-storage.md) for the exact environment variables, validation steps, and handling of existing missing images. No frontend release or database migration is needed for this switch.
