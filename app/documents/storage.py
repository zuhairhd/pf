"""Safe document storage helpers."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import List

from fastapi import HTTPException, UploadFile

from app.config import Settings


# Whitelist: extension (without dot, lower) -> MIME types
_ALLOWED_MIME_TYPES = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "webp": {"image/webp"},
    "txt": {"text/plain", "text/x-python", "application/octet-stream"},
    "csv": {"text/csv", "application/csv", "text/plain", "application/octet-stream"},
}


def _allowed_extensions(settings: Settings) -> List[str]:
    return [ext.strip().lower() for ext in settings.DOCUMENT_ALLOWED_EXTENSIONS.split(",")]


def _extension_for(filename: str) -> str:
    """Return the lower-case extension without the leading dot."""
    ext = Path(filename).suffix.lstrip(".").lower()
    return ext


def _sanitize_filename(filename: str) -> str:
    """Return a safe original-filename string with path separators removed."""
    name = Path(filename).name
    # Remove any null bytes and strip whitespace
    name = name.replace("\x00", "").strip()
    return name


def validate_upload(file: UploadFile, settings: Settings) -> None:
    """Validate uploaded file extension, MIME type, and size.

    Raises HTTPException with 400 or 413 on rejection.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Missing filename")

    original_name = _sanitize_filename(file.filename)
    ext = _extension_for(original_name)
    allowed = _allowed_extensions(settings)

    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' is not allowed. Allowed: {', '.join(allowed)}",
        )

    content_type = (file.content_type or "application/octet-stream").lower()
    content_type = content_type.split(";")[0].strip()
    valid_mimes = _ALLOWED_MIME_TYPES.get(ext, set())
    if content_type not in valid_mimes:
        # Some clients send generic content types; reject anything clearly wrong.
        # We still allow application/octet-stream for text/csv if extension matches.
        if content_type != "application/octet-stream" or ext not in {"txt", "csv"}:
            raise HTTPException(
                status_code=400,
                detail=f"MIME type '{content_type}' is not allowed for .{ext} files",
            )

    max_size = settings.DOCUMENT_MAX_UPLOAD_MB * 1024 * 1024
    # FastAPI UploadFile exposes a spooled temporary file; we cannot know the
    # size without reading. Validation of the actual size happens during read.
    file_size_hint = getattr(file, "size", None)
    if file_size_hint is not None and file_size_hint > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.DOCUMENT_MAX_UPLOAD_MB} MB",
        )


def _tenant_upload_dir(settings: Settings, tenant_id: int) -> Path:
    """Return (and create) the tenant-specific upload directory."""
    base = Path(settings.DOCUMENT_UPLOAD_DIR).expanduser()
    if not base.is_absolute():
        base = Path.cwd() / base
    tenant_dir = base.resolve() / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir


def compute_checksum(content: bytes) -> str:
    """Return the SHA-256 hex digest of the file content."""
    return hashlib.sha256(content).hexdigest()


def generate_stored_filename(extension: str) -> str:
    """Return a unique stored filename with the given extension."""
    ext = extension.lstrip(".").lower()
    return f"{uuid.uuid4().hex}.{ext}"


def save_upload(
    file: UploadFile,
    tenant_id: int,
    settings: Settings,
) -> dict:
    """Validate, read, and persist an uploaded file.

    Returns a dict with: original_filename, filename_stored, file_size,
    mime_type, storage_path, checksum.
    """
    validate_upload(file, settings)

    original_name = _sanitize_filename(file.filename or "unnamed")
    ext = _extension_for(original_name)
    filename_stored = generate_stored_filename(ext)

    tenant_dir = _tenant_upload_dir(settings, tenant_id)
    file_path = tenant_dir / filename_stored

    content_type = (file.content_type or "application/octet-stream").lower()
    content_type = content_type.split(";")[0].strip()

    content = file.file.read()
    if not isinstance(content, bytes):
        content = content.encode("utf-8")

    max_size = settings.DOCUMENT_MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.DOCUMENT_MAX_UPLOAD_MB} MB",
        )

    checksum = compute_checksum(content)

    with open(file_path, "wb") as f:
        f.write(content)

    # Store a relative path for portability.
    storage_path = f"{settings.DOCUMENT_UPLOAD_DIR}/{tenant_id}/{filename_stored}"

    return {
        "original_filename": original_name,
        "filename_stored": filename_stored,
        "file_size": len(content),
        "mime_type": content_type,
        "storage_path": storage_path,
        "checksum": checksum,
    }


def resolve_storage_path(storage_path: str) -> Path:
    """Resolve a stored relative path to an absolute filesystem path."""
    path = Path(storage_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def delete_file(storage_path: str) -> None:
    """Delete a stored file if it exists."""
    path = resolve_storage_path(storage_path)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        # Best-effort deletion; do not fail if the file is already gone.
        pass
