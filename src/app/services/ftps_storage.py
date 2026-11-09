"""Durable upload storage using explicit FTPS and a restricted remote account."""
from contextlib import contextmanager
from ftplib import FTP, FTP_TLS, all_errors, error_perm
import io
import ssl
from tempfile import SpooledTemporaryFile
from threading import BoundedSemaphore
from uuid import UUID
from fastapi import HTTPException
from app.core.config import settings
from app.core.logging import logger

MAX_STORED_FILE_BYTES = 50 * 1024 * 1024
CONNECTION_SLOTS = BoundedSemaphore(3)


class SecureFTP(FTP_TLS):
    def ntransfercmd(self, cmd, rest=None):
        # Some FTPS servers require data channels to reuse the authenticated TLS session.
        connection, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            try:
                connection = self.context.wrap_socket(connection, server_hostname=self.host,
                                                      session=self.sock.session)
            except Exception:
                connection.close()
                raise
        return connection, size


@contextmanager
def connection():
    if not CONNECTION_SLOTS.acquire(timeout=settings.ftps_timeout_seconds):
        raise HTTPException(503, 'File storage is busy. Please try again.')
    ftp = None
    try:
        ftp = SecureFTP(context=ssl.create_default_context(), timeout=settings.ftps_timeout_seconds)
        ftp.connect(settings.ftps_host, settings.ftps_port)
        ftp.auth()
        ftp.login(settings.ftps_username, settings.ftps_password.get_secret_value())
        ftp.prot_p()
        ftp.set_pasv(True)
        ftp.cwd(settings.ftps_root)
        yield ftp
    finally:
        try:
            if ftp is not None: ftp.close()
        finally:
            CONNECTION_SLOTS.release()


def filename(identifier):
    # User-provided filenames are metadata only and are never remote path components.
    try:
        if str(UUID(identifier)) != identifier:
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(404, 'File not found')
    return identifier


def folder(private):
    return 'private' if private else 'public'


def store(identifier, raw, private):
    name = filename(identifier)
    temporary = name + '.part'
    try:
        with connection() as ftp:
            directory = folder(private)
            try:
                ftp.cwd(directory)
            except error_perm:
                try:
                    ftp.mkd(directory)
                except error_perm:
                    pass  # Another worker may have created it; cwd verifies access.
                ftp.cwd(directory)
            try:
                ftp.storbinary('STOR ' + temporary, io.BytesIO(raw))
                ftp.rename(temporary, name)
            except Exception:
                try:
                    ftp.delete(temporary)
                except all_errors:
                    pass
                raise
    except all_errors as error:
        logger.warning('Remote upload storage failed: %s', type(error).__name__)
        raise HTTPException(503, 'Upload storage is unavailable. Please try again or contact the organiser.') from None


def retrieve(identifier, private):
    """Return a bounded temporary stream, or None if the remote file is missing."""
    name = filename(identifier)
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode='w+b')
    def write(chunk):
        if output.tell() + len(chunk) > MAX_STORED_FILE_BYTES:
            raise HTTPException(503, 'File is larger than the supported storage limit')
        output.write(chunk)
    try:
        with connection() as ftp:
            try:
                ftp.cwd(folder(private))
                ftp.retrbinary('RETR ' + name, write)
            except error_perm as error:
                if str(error).startswith('550'):
                    output.close()
                    return None
                raise
        output.seek(0)
        return output
    except all_errors as error:
        output.close()
        logger.warning('Remote download storage failed: %s', type(error).__name__)
        raise HTTPException(503, 'File storage is unavailable. Please try again.') from None
    except Exception:
        output.close()
        raise
