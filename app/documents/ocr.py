"""OCR/text extraction engine abstraction.

The module is designed so that plain text and CSV extraction works without any
external system binaries. PDF text extraction uses the pure-Python PyPDF2
library when available. Image OCR is optional and only runs when explicitly
enabled and pytesseract/tesseract are installed.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.config import Settings


@dataclass
class OCRResult:
    """Result of an OCR/text extraction attempt."""

    text: Optional[str]
    status: str  # processed, unsupported, failed
    confidence: Optional[float]
    error: Optional[str]


def _decode_text(content: bytes) -> str:
    """Decode bytes as UTF-8, falling back to latin-1."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


class OCREngine(ABC):
    """Base class for OCR/text extraction engines."""

    @abstractmethod
    def can_process(self, mime_type: str, settings: Settings) -> bool:
        """Return True if this engine can handle the given MIME type."""
        ...

    @abstractmethod
    def extract(self, content: bytes, mime_type: str, settings: Settings) -> OCRResult:
        """Attempt to extract text from the content."""
        ...


class TextFileOCREngine(OCREngine):
    """Direct text decoding for plain text and CSV files."""

    _SUPPORTED = {
        "text/plain",
        "text/csv",
        "application/csv",
        "text/x-python",
    }

    def can_process(self, mime_type: str, settings: Settings) -> bool:
        normalized = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
        return normalized in self._SUPPORTED

    def extract(self, content: bytes, mime_type: str, settings: Settings) -> OCRResult:
        try:
            text = _decode_text(content)
            return OCRResult(text=text, status="processed", confidence=1.0, error=None)
        except Exception as exc:  # pragma: no cover - decoding is very unlikely to fail
            return OCRResult(text=None, status="failed", confidence=None, error=str(exc))


class PDFTextExtractionEngine(OCREngine):
    """Extract embedded text from PDF files using PyPDF2 when available."""

    def can_process(self, mime_type: str, settings: Settings) -> bool:
        if not settings.OCR_ALLOW_PDF_TEXT_EXTRACTION:
            return False
        normalized = (mime_type or "application/octet-stream").lower().split(";")[0].strip()
        return normalized == "application/pdf"

    def extract(self, content: bytes, mime_type: str, settings: Settings) -> OCRResult:
        try:
            from PyPDF2 import PdfReader
        except Exception as exc:  # pragma: no cover - import failure path
            return OCRResult(
                text=None,
                status="unsupported",
                confidence=None,
                error=f"PyPDF2 not available: {exc}",
            )

        try:
            reader = PdfReader(io.BytesIO(content))
            parts: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    parts.append(page_text)
            text = "\n".join(parts).strip() or None
            return OCRResult(text=text, status="processed", confidence=None, error=None)
        except Exception as exc:
            return OCRResult(text=None, status="failed", confidence=None, error=str(exc))


class ImageTesseractOCREngine(OCREngine):
    """Optional image OCR through pytesseract."""

    def can_process(self, mime_type: str, settings: Settings) -> bool:
        if not settings.OCR_ENABLED or not settings.OCR_ALLOW_IMAGE_OCR:
            return False
        normalized = (mime_type or "application/octet-stream").lower()
        return normalized.startswith("image/")

    def extract(self, content: bytes, mime_type: str, settings: Settings) -> OCRResult:
        try:
            from PIL import Image
            import pytesseract
        except Exception as exc:  # pragma: no cover - depends on system deps
            return OCRResult(
                text=None,
                status="unsupported",
                confidence=None,
                error=f"Image OCR dependencies not available: {exc}",
            )

        try:
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image).strip() or None
            return OCRResult(text=text, status="processed", confidence=None, error=None)
        except Exception as exc:
            return OCRResult(text=None, status="failed", confidence=None, error=str(exc))


class OCRProcessor:
    """Runs registered OCR engines and returns the first successful result."""

    _DEFAULT_ENGINES: list[OCREngine] = [
        TextFileOCREngine(),
        PDFTextExtractionEngine(),
        ImageTesseractOCREngine(),
    ]

    def __init__(self, engines: Optional[list[OCREngine]] = None):
        self.engines = engines if engines is not None else list(self._DEFAULT_ENGINES)

    def process(self, content: bytes, mime_type: str, settings: Settings) -> OCRResult:
        """Extract text using the first compatible engine.

        If no engine can process the MIME type, returns an ``unsupported``
        result. Extracted text is truncated to ``OCR_MAX_TEXT_LENGTH``.
        """
        for engine in self.engines:
            if engine.can_process(mime_type, settings):
                result = engine.extract(content, mime_type, settings)
                if result.text is not None and settings.OCR_MAX_TEXT_LENGTH:
                    result.text = result.text[: settings.OCR_MAX_TEXT_LENGTH]
                return result

        return OCRResult(
            text=None,
            status="unsupported",
            confidence=None,
            error=f"No OCR engine available for MIME type {mime_type}",
        )


# Backwards-compatible helper used by older call sites.
def extract_text(
    content: bytes,
    mime_type: str,
    settings: Settings,
) -> tuple[Optional[str], str, Optional[float], Optional[str]]:
    """Extract text from supported document content.

    Returns a tuple of (text, status, confidence, error).
    """
    result = OCRProcessor().process(content, mime_type, settings)
    return result.text, result.status, result.confidence, result.error
