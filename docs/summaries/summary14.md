> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 21: DOC-2100 — Document OCR / Document Management Enhancement**.

# Summary 14 — Card 21: DOC-2100 Document OCR / Document Management Enhancement

## What Was Done

Hardened document management so users can upload receipts, statements, and other financial documents safely, with OCR-ready metadata and optional entity linking.

## Key Changes

- Extended `Document` model with `filename_stored`, `category`, `checksum`, `uploaded_by_user_id`, `status`, `ocr_status`, `ocr_error`, `related_entity_type`, and `related_entity_id`.
- Created Alembic migration `5e8169dd3017` with safe defaults, backfill, indexes, and a foreign key to `users`.
- Added `app/documents/` package:
  - `storage.py` — safe upload validation, tenant-scoped directories, checksums, filename sanitization, file serving/deletion.
  - `ocr.py` — text extraction for plain text/CSV; optional pytesseract image OCR; safe fallback when disabled.
  - `services.py` — `DocumentService` for upload, list, get, update, archive, delete, OCR, link, unlink, and cross-tenant entity validation.
- Added `app/schemas/document.py` with create/update/link/response schemas.
- Rewrote `app/routers/documents.py` with auth + tenant-context dependencies for all endpoints.
- Switched `app/routers/transactions.py` write endpoints to `get_db_with_tenant_context` and `require_tenant_member` to fix RLS violations when linking documents to journal entries.
- Moved document service logic out of `app/services/document_service.py` into `app/documents/services.py`.
- Added config keys for document upload and OCR with `.env.example` placeholders.
- Added 16 integration tests in `app/tests/integration/test_documents.py`.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest --tb=no --disable-warnings` — **252 passed, 1 skipped**

## Next Recommended Card

**DOC-2101 — OCR Engine Integration**
