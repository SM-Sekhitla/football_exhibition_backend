# Durable uploads on Sivehost

Render runs the API and stores upload metadata in PostgreSQL. The restricted Sivehost FTPS account stores file bytes outside public_html. Images and documents keep their existing /api/v1/files/{id} URLs, so no frontend release or database migration is required for this storage switch.

## Render environment

Deploy the backend code containing FTPS storage support and configure:

```dotenv
UPLOAD_STORAGE=ftps
FTPS_HOST=ftp.best5football.co.za
FTPS_PORT=21
FTPS_USERNAME=best5uploads@best5football.co.za
FTPS_PASSWORD=the-password-of-the-restricted-upload-account
FTPS_ROOT=/
FTPS_TIMEOUT_SECONDS=20
```

Use the password of the restricted upload account, not the main hosting account. Keep it in Render's environment settings (and an ignored local backend .env only if needed), never in the frontend or Git. Preserve DATABASE_URL, email credentials and all other existing settings.

The FTP account is already jailed to the server folder /home/<hosting-user>/domains/best5football.co.za/best5_uploads. Therefore FTPS_ROOT is /, not the full server path. The backend creates public/ and private/ inside this jail. Both folders are outside the website document root. The word public indicates that the API allows public downloads; the private files still require an authorized administration session before any remote access.

## Connection and transfer behavior

Explicit FTPS on port 21 verifies the host certificate and encrypts control/data connections. Passive data connections are required. TLS session reuse supports servers that require it on the data channel. Concurrent connections are limited to three per API worker. If Sivehost refuses connections or runs out of quota, uploads return an error; they never silently fall back to Render's temporary filesystem. Failed temporary transfers are cleaned up where possible, and a final filename is published by rename only after upload completes.

Downloads use a bounded temporary stream, removed when the response completes. These temporary files are not the durable storage. Existing access control and no-store headers remain for POP downloads. The database must remain persistent, because it contains ownership and file metadata.

## Verify after deployment

1. Upload a small image through Media.
2. In Sivehost File Manager, check best5_uploads/public for a UUID-named file. Do not move it into public_html.
3. Verify the image loads, then redeploy the Render service and refresh. It should still load.
4. For a legitimate team application, confirm the POP appears in best5_uploads/private and can be downloaded by an authorized admin, but not by a signed-out browser.
5. Monitor Sivehost disk usage; its 1 GB allowance also includes website and mailbox data. Back up the upload directory and database together.

## Existing uploads

The switch does not recover files already deleted by Render. Remaining local files can still be downloaded while present, but are not automatically copied to Sivehost. Back them up before another deployment. To preserve an existing file's URL when manually restoring a backup, retain its UUID filename and put it in public/ for images or private/ for payment proofs. The corresponding Upload database row must also still exist. If originals are reuploaded through the UI, update the affected gallery/landing/sponsor image selections to use the new uploads. Do not delete database records or reset the database to address missing files.

Do not use UPLOAD_STORAGE=local on the live ephemeral Render filesystem after switching to durable uploads. Leave local mode enabled for automated tests and ordinary local development.

## Back up a free Render service without Shell access

Do this before deploying code or saving new Render environment settings. From the backend repository root on your computer:

```bash
src/.venv/bin/python src/scripts/backup_uploads.py
```

Enter your live admin email and password when prompted. Password input is hidden. The script uses the current admin API, needs no new deployed endpoint, sends no email, and does not change settings. It creates a separate login session and attempts to log that session out afterward. Use an account with both content and registration read permissions.

The private local backups/ folder contains timestamped public/{uuid} and private/{uuid} files, an admin snapshot, a manifest listing failures and SHA-256 checksums, and a backup ZIP. The backup ZIP is not a frontend release. Check the counts and uploads-manifest.json before redeploying. Missing files cannot be recovered from Render by this script. It captures referenced files in admin-visible data, not orphaned uploads or static frontend assets. It is not a complete PostgreSQL dump and does not back up accounts, sessions, or all audit records.

To restore existing file URLs, upload and extract this backup ZIP inside Sivehost's best5_uploads directory outside public_html, preserving public/ and private/ and UUID filenames. Remove the uploaded backup ZIP after extraction to avoid keeping a second full copy in the hosting quota. Keep a local backup. Only enable UPLOAD_STORAGE=ftps after verifying the restored files and checking the failure manifest. The existing database metadata must be retained.
