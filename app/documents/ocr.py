"""Lightweight OCR/text extraction helpers."""

from __future__ import annotations

from typing import Optional, Tuple

from app.config import Settings


def _decode_text(content: bytes) -> str:
    """Decode bytes as UTF-8, falling back to latin-1."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def extract_text(
    content: bytes,
    mime_type: str,
    settings: Settings,
) -> Tuple[Optional[str], str, Optional[float], Optional[str]]:
    """Extract text from supported document content.

    Returns a tuple of (text, status, confidence, error).
    """
    normalized = (mime_type or "application/octet-stream").lower()

    if normalized in {"text/plain", "text/csv", "application/csv", "text/x-python"}:
        text = _decode_text(content)
        return text, "success", 1.0, None

    if not settings.OCR_ENABLED:
        return None, "unsupported", None, "OCR is disabled"

    # Optional pytesseract-based OCR for images. Not required for tests.
    if normalized.startswith("image/"):
        try:
            from PIL import Image
            import pytesseract

            image = Image.open(__import__("io").BytesIO(content))
            text = pytesseract.image_to_string(image)
            return text, "success", None, None
        except Exception as exc:  # pragma: no cover - depends on system deps
            return None, "failed", None, str(exc)

    return None, "unsupported", None, f"OCR not supported for MIME type {mime_type}"
