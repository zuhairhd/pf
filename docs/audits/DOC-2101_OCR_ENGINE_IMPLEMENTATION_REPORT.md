# DOC-2101 — OCR Engine Integration

## Summary

Integrated a stronger OCR engine layer into the document management module. The new `app/documents/ocr.py` provides an engine abstraction with separate handlers for plain text/CSV, PDF text extraction (via PyPDF2), and optional image OCR (via pytesseract). New configuration variables control feature flags, text length limits, and timeouts. The `POST /documents/{document_id}/ocr` endpoint now returns a dedicated OCR result payload with status, extracted text preview, and error details. All access remains authenticated, tenant-scoped, and RLS-safe. No system OCR binaries are required for normal tests.

## Files Changed

- `app/documents/ocr.py` — completely refactored into `OCRResult`, `OCREngine` base class, `TextFileOCREngine`, `PDFTextExtractionEngine`, `ImageTesseractOCREngine`, `OCRProcessor`, and backwards-compatible `extract_text` helper.
- `app/documents/storage.py` — added `is_path_within_tenant_dir()` helper to verify a stored path stays inside the tenant upload directory.
- `app/documents/services.py` — updated `DocumentService.run_ocr()` to use `OCRProcessor`, set `ocr_status=processing`, enforce path safety, truncate text to `OCR_MAX_TEXT_LENGTH`, and store `failed`/`unsupported` statuses safely.
- `app/schemas/document.py` — added `OCRResultResponse` schema.
- `app/routers/documents.py` — updated `POST /documents/{document_id}/ocr` to return `OCRResultResponse` with a text preview and without leaking filesystem paths.
- `app/config.py` — added `OCR_ENGINE`, `OCR_MAX_TEXT_LENGTH`, `OCR_TIMEOUT_SECONDS`, `OCR_ALLOW_IMAGE_OCR`, `OCR_ALLOW_PDF_TEXT_EXTRACTION`.
- `.env.example` — added placeholders for the new OCR configuration variables.
- `requirements.txt` — added `PyPDF2`.
- `app/tasks/document_ocr.py` — added Celery task stub `process_document_ocr_task(document_id, tenant_id)`.
- `app/tasks/celery_app.py` — included `app.tasks.document_ocr` in Celery include list.
- `app/tests/integration/test_documents.py` — updated existing OCR tests for new statuses and added tests for CSV, PDF, truncation, missing file, auth, tenant isolation, and path-leak prevention.

## Config Variables Added

| Variable | Default | Purpose |
|----------|---------|---------|
| `OCR_ENGINE` | `auto` | Reserved engine selector (currently only `auto`) |
| `OCR_MAX_TEXT_LENGTH` | `100000` | Maximum characters stored per OCR run |
| `OCR_TIMEOUT_SECONDS` | `30` | Reserved timeout hint for future async engines |
| `OCR_ALLOW_IMAGE_OCR` | `False` | Enable/disable image OCR via pytesseract |
| `OCR_ALLOW_PDF_TEXT_EXTRACTION` | `True` | Enable/disable PyPDF2 text extraction |

## OCR Engines Implemented

1. **TextFileOCREngine** — always active. Decodes `text/plain`, `text/csv`, `application/csv`, and `text/x-python` as UTF-8 (with latin-1 fallback). Confidence is `1.0`.
2. **PDFTextExtractionEngine** — active when `OCR_ALLOW_PDF_TEXT_EXTRACTION=True`. Uses PyPDF2 to extract embedded text from PDF pages. Returns `unsupported` if PyPDF2 is unavailable.
3. **ImageTesseractOCREngine** — active only when `OCR_ENABLED=True` **and** `OCR_ALLOW_IMAGE_OCR=True`. Uses Pillow + pytesseract. Returns `unsupported` or `failed` if dependencies/binary are missing.
4. **OCRProcessor** — selects the first compatible engine and truncates the result to `OCR_MAX_TEXT_LENGTH`.

## OCR Status Behavior

- `processing` — set while OCR is running.
- `processed` — text was extracted successfully.
- `unsupported` — MIME type is not handled or the engine is disabled/unavailable.
- `failed` — an unexpected error occurred (missing file, extraction exception, path outside tenant dir).

No database migration was required because `Document.ocr_status` is already a `String(20)` nullable column.

## PDF/Image Limitations

- PDF extraction relies on PyPDF2 and only returns text that is embedded in the PDF. Scanned/image-based PDFs will return empty or no text unless an image-OCR pipeline is added later.
- Image OCR requires both `OCR_ENABLED=true`, `OCR_ALLOW_IMAGE_OCR=true`, and a working Tesseract installation. It is disabled by default so tests do not depend on system binaries.
- `OCR_TIMEOUT_SECONDS` is currently a configuration placeholder; the synchronous engine does not enforce it.

## Route Behavior

`POST /documents/{document_id}/ocr` now returns:

```json
{
  "document_id": 123,
  "ocr_status": "processed",
  "ocr_text": "...",
  "text_preview": "... first 500 chars ...",
  "ocr_error": null,
  "updated_at": "2026-07-11T..."
}
```

The response never includes `storage_path` or local filesystem details.

## Background Task Behavior

- Added `app/tasks/document_ocr.py::process_document_ocr_task(document_id, tenant_id)` as a Celery task stub.
- The stub logs intent and returns a `not_implemented` placeholder.
- Full background processing requires a Celery worker with sync DB session + RLS context setup; this is documented as a future improvement.

## RLS/Tenant Safety

- The service always fetches the document by `id` **and** `tenant_id`, so cross-tenant OCR attempts return `404`.
- The stored file path is verified to lie inside `uploads/documents/{tenant_id}` before reading.
- All routes continue to use `get_db_with_tenant_context` + `require_tenant_member`.
- The `documents` table remains RLS-enabled.

## Test Results

- Updated/added integration tests in `app/tests/integration/test_documents.py`: 23 tests.
- Full suite: **259 passed, 1 skipped**.

Covered scenarios:
- Text file OCR extracts and stores text (`processed`)
- CSV file OCR extracts text
- PDF text extraction works when PyPDF2 is available
- Unsupported image (PNG) returns `unsupported` when image OCR is disabled
- Long OCR text is truncated to `OCR_MAX_TEXT_LENGTH`
- Missing stored file returns `failed`
- OCR requires authentication
- Tenant A cannot OCR Tenant B document
- OCR response does not leak filesystem paths
- Existing upload/validation/linking/RLS tests still pass

## Known Limitations

- No structured receipt parsing (date/amount/merchant) yet; OCR returns raw text only.
- Image OCR is opt-in and depends on external Tesseract.
- `OCR_TIMEOUT_SECONDS` is not enforced by the synchronous engines.
- Background Celery task is a stub; production async OCR not wired.

## Recommended Next Card

**AI-1214 — What-If Simulator**: build on the financial core and reports to let users simulate changes to income, expenses, or debt payments and see projected outcomes.
