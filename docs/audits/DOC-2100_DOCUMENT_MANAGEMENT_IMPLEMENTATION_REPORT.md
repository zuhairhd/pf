# DOC-2100 — Document OCR / Document Management Enhancement

## Summary

Enhanced the document management module so users can upload receipts, statements, and other financial documents safely. The `documents` table was hardened with upload metadata, OCR-ready fields, generic entity linking, and tenant-scoped storage. A new `app/documents/` package provides validation, safe file storage, lightweight OCR/text extraction, and linking to transactions, bills, subscriptions, and goals. All routes require authentication and tenant membership and use `get_db_with_tenant_context` so RLS remains enforced. The full test suite passes with the new integration tests.

## Files Changed

- `app/models/document.py` — added `filename_stored`, `category`, `checksum`, `uploaded_by_user_id`, `status`, `ocr_status`, `ocr_error`, `related_entity_type`, `related_entity_id`, indexes, and uploader relationship.
- `app/models/__init__.py` — exported `DocumentStatus`.
- `app/config.py` — added `DOCUMENT_UPLOAD_DIR`, `DOCUMENT_MAX_UPLOAD_MB`, `DOCUMENT_ALLOWED_EXTENSIONS`, `OCR_ENABLED`, `OCR_DEV_MODE`.
- `.env.example` — added document and OCR configuration placeholders.
- `app/documents/__init__.py` — package init.
- `app/documents/storage.py` — safe upload validation, tenant-scoped file storage, filename sanitization, checksums, path resolution, deletion.
- `app/documents/ocr.py` — lightweight text extraction for plain text/CSV; optional pytesseract image OCR when enabled; safe fallback for unsupported types.
- `app/documents/services.py` — `DocumentService` with upload, list, get, update, archive, delete, OCR, link, unlink, and cross-tenant entity validation.
- `app/schemas/document.py` — `DocumentCreate`, `DocumentUpdate`, `DocumentLinkRequest`, `DocumentResponse`.
- `app/schemas/__init__.py` — exported document schemas.
- `app/routers/documents.py` — rewrote with auth + tenant-context dependencies; endpoints for upload, list, get, download, update, delete, archive, OCR, link, unlink.
- `app/routers/transactions.py` — switched write endpoints to `get_db_with_tenant_context` and `require_tenant_member` so journal entries can be created without RLS violations when linking documents.
- `app/services/document_service.py` — removed; logic moved to `app/documents/services.py`.
- `app/services/__init__.py` — updated exports.
- `app/tests/integration/test_documents.py` — new integration tests for upload, validation, OCR, linking, tenant isolation, and RLS.

## Model/Schema Changes

The `documents` table gained:

| Column | Type | Purpose |
|--------|------|---------|
| `filename_stored` | `String(255)` | Safe unique stored filename |
| `category` | `String(50)` | User-defined category |
| `checksum` | `String(64)` | SHA-256 of file content |
| `uploaded_by_user_id` | `Integer FK -> users.id` | Uploader |
| `status` | `String(20)` | `uploaded` / `processing` / `processed` / `failed` / `archived` |
| `ocr_status` | `String(20)` | OCR result status |
| `ocr_error` | `Text` | OCR error message |
| `related_entity_type` | `String(50)` | `transaction`, `bill`, `subscription`, `goal` |
| `related_entity_id` | `Integer` | ID of linked entity |

Indexes added:
- `ix_documents_category`
- `ix_documents_checksum`
- `ix_documents_related_entity_id`
- `ix_documents_related_entity_type`
- `ix_documents_status`
- `ix_documents_uploaded_by_user_id`
- `ix_documents_tenant_status`
- `ix_documents_tenant_uploader`
- `ix_documents_tenant_related_entity`

Foreign key added from `documents.uploaded_by_user_id` to `users.id`.

## Alembic Revision ID

- **Revision:** `5e8169dd3017`
- **Down revision:** `33f87e4863be`
- **File:** `alembic/versions/5e8169dd3017_harden_document_model_for_upload_ocr_.py`

The migration preserves existing rows by backfilling `filename_stored` from the legacy `filename` column. It does not drop or recreate the `documents` table, and it leaves existing RLS policies in place.

## Upload/Storage Behavior

- Files are saved under `uploads/documents/{tenant_id}/{stored_filename}`.
- Stored filenames are UUID-based with the original extension; original filenames are sanitized and stored for display only.
- Relative storage paths are persisted for portability and resolved to absolute paths at read time.
- File deletion removes both the database row and the stored file.
- Tenant directories are created on demand.

## File Validation Rules

- Allowed extensions (configurable via `DOCUMENT_ALLOWED_EXTENSIONS`): `pdf`, `png`, `jpg`, `jpeg`, `webp`, `txt`, `csv`.
- MIME type is checked against a whitelist per extension; generic `application/octet-stream` is accepted only for `txt`/`csv`.
- Maximum file size is enforced from `DOCUMENT_MAX_UPLOAD_MB` (default 10 MB) both from the client hint and after reading content.
- Filenames are sanitized: path separators, null bytes, and surrounding whitespace are removed.
- Path traversal attempts (e.g., `../evil.txt`) are reduced to the basename.

## OCR Behavior

- Plain text and CSV files are decoded directly with `ocr_status = "success"` and confidence `1.0`.
- When `OCR_ENABLED` is `False`, image/PDF OCR returns `ocr_status = "unsupported"` without failing.
- If `OCR_ENABLED` is `True` and `pytesseract`/`Pillow` are available, image OCR is attempted; failures are captured in `ocr_error` with `ocr_status = "failed"`.
- Unsupported MIME types return `ocr_status = "unsupported"` safely.

## Linking Behavior

Documents can be linked at upload time or later to:

- `transaction` (`JournalEntry`)
- `bill` (`Bill`)
- `subscription` (`Subscription`)
- `goal` (`Goal`)

Validation ensures the target entity exists and belongs to the same tenant. Cross-tenant linking returns `404`. Unsupported entity types return `400`. The `unlink` endpoint clears the link.

## Routes Added/Updated

All routes are under `/documents` and require a valid JWT + tenant membership.

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/documents/` | List non-archived tenant documents |
| POST | `/documents/upload` | Upload a document with optional metadata/link |
| GET | `/documents/{document_id}` | Get document metadata |
| GET | `/documents/{document_id}/download` | Download the stored file |
| PATCH | `/documents/{document_id}` | Update metadata |
| DELETE | `/documents/{document_id}` | Delete document + file |
| POST | `/documents/{document_id}/archive` | Mark document as archived |
| POST | `/documents/{document_id}/ocr` | Run OCR/text extraction |
| POST | `/documents/{document_id}/link` | Link to a tenant entity |
| POST | `/documents/{document_id}/unlink` | Remove entity link |

## RLS/Tenant Safety

- All document service queries filter by `tenant_id`.
- Routes use `get_db_with_tenant_context`, which sets the RLS tenant context from the JWT.
- The `documents` table retains RLS + FORCE RLS; `test_rls_active_on_documents_table` verifies this.
- Cross-tenant access tests confirm Tenant A cannot read, download, or list Tenant B documents.
- Cross-tenant linking tests confirm Tenant A cannot link a document to Tenant B's entity.
- Files are stored in tenant-isolated directories and served only after auth/tenant checks.

## Test Results

- New integration tests in `app/tests/integration/test_documents.py`: 16 tests.
- Full suite: **252 passed, 1 skipped**.

Covered scenarios:
- Upload requires auth
- Valid upload creates a document row with checksum
- Unsupported extension rejected
- Oversized file rejected (413)
- Path traversal sanitized
- List/get/download scoped to tenant
- Archive hides document from list
- Delete removes document and file
- Text OCR extraction succeeds
- Unsupported OCR type handled safely
- Link/unlink to bill and transaction
- Unsupported entity type rejected
- Cross-tenant document access rejected
- Cross-tenant linking rejected
- RLS active on `documents`

## Known Limitations

- Full AI receipt parsing (date, amount, merchant extraction) is not implemented; OCR returns raw text only.
- Image/PDF OCR requires an external engine such as Tesseract and is disabled by default (`OCR_ENABLED=false`).
- Document linking does not yet enforce object-level permissions beyond tenant membership (e.g., private goal visibility is not checked when linking).
- No full-text search or document indexing yet.
- Cloud storage integration is not implemented; files remain on local disk.

## Recommended Next Card

**DOC-2101 — OCR Engine Integration**: add a real OCR backend (e.g., Tesseract or cloud vision) for images/PDFs and extract structured receipt fields (date, amount, merchant) with safety filters.
