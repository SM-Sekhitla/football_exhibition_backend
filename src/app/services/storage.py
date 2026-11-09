import base64
import binascii
import io
from pathlib import Path
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from app.core.config import settings
from app.db.models import Upload


def save_upload(db, name, mime, data, private=False, owner=None):
    try:
        prefix, encoded = data.split(',', 1)
        if prefix != f'data:{mime};base64': raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, 'Invalid upload encoding')
    limit = (settings.max_document_size_mb if private else settings.max_branding_image_size_mb) * 1024 * 1024
    if mime not in (settings.proof_types if private else settings.image_types): raise HTTPException(422, 'This file type is disabled in the server configuration')
    if not raw or len(raw) > limit: raise HTTPException(422, 'Upload exceeds allowed size')
    if mime == 'application/pdf':
        if not private or not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-2048:]:
            raise HTTPException(422, 'Invalid PDF file')
    else:
        try:
            expected = {'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP','image/gif':'GIF','image/avif':'AVIF'}
            if mime not in expected: raise ValueError()
            with Image.open(io.BytesIO(raw),formats=[expected[mime]]) as image:
                if image.width * image.height > 40_000_000: raise ValueError()
                if image.format != expected.get(mime): raise ValueError()
                image.verify()
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            raise HTTPException(422, 'Invalid or oversized image file')
    identifier = str(uuid4())
    if settings.upload_storage == 'ftps':
        from app.services.ftps_storage import store
        store(identifier, raw, private)
    else:
        directory = settings.storage_dir if private else settings.branding_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / identifier
        path.write_bytes(raw); path.chmod(0o600)
    db.add(Upload(id=identifier, name=Path(name).name[:200], mime=mime, private=private, owner_record=owner))
    return {'id': identifier, 'name': Path(name).name[:200], 'type': mime, 'data': f'{settings.api_v1_prefix}/files/{identifier}', 'src': f'{settings.api_v1_prefix}/files/{identifier}'}
