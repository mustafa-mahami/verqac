"""File storage on local disk (a Docker volume). Same interface can later move to S3/MinIO.

Files are addressed by an opaque key, never by the uploaded name, and stored outside
any web root: the only way to read one is the API, which checks access first.
"""
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

CHUNK = 1024 * 1024


def _root() -> Path:
    root = Path(get_settings().files_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(project_id: uuid.UUID, upload: UploadFile) -> tuple[str, int, str]:
    """Stream to disk while hashing. Returns (storage_key, size, sha256)."""
    limit = get_settings().max_upload_mb * CHUNK
    key = f"{project_id}/{uuid.uuid4().hex}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    try:
        with open(path, "wb") as out:
            while chunk := upload.file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
                digest.update(chunk)
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_empty")
    return key, size, digest.hexdigest()


def path_of(key: str) -> Path:
    path = (_root() / key).resolve()
    if not str(path).startswith(str(_root().resolve()) + os.sep) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return path


def delete(key: str) -> None:
    (_root() / key).unlink(missing_ok=True)
