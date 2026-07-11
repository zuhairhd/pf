> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 22: DOC-2101 — OCR Engine Integration**.

# Summary 15 — Card 22: DOC-2101 OCR Engine Integration

## What Was Done

Refactored document OCR into a pluggable engine abstraction and added PDF text extraction while keeping image OCR optional and system-binary-free by default.

## Key Changes

- Refactored `app/documents/ocr.py`:
  - `OCRResult` dataclass
  - `OCREngine` abstract base class
  - `TextFileOCREngine` for `txt`/`csv`
  - `PDFTextExtractionEngine` using PyPDF2
  - `ImageTesseractOCREngine` (opt-in, requires `OCR_ALLOW_IMAGE_OCR=true` and Tesseract)
  - `OCRProcessor` that selects the first compatible engine and truncates output
- Added `OCRResultResponse` schema and updated `POST /documents/{id}/ocr` to return it.
- Added config variables: `OCR_ENGINE`, `OCR_MAX_TEXT_LENGTH`, `OCR_TIMEOUT_SECONDS`, `OCR_ALLOW_IMAGE_OCR`, `OCR_ALLOW_PDF_TEXT_EXTRACTION`.
- Updated `.env.example` and `requirements.txt` (added `PyPDF2`).
- Updated `DocumentService.run_ocr()` to set `ocr_status=processing`, verify the stored path is inside the tenant upload directory, truncate text, and handle failures safely.
- Added Celery task stub `process_document_ocr_task` in `app/tasks/document_ocr.py`.
- Updated/expanded `app/tests/integration/test_documents.py` with OCR-focused tests.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest --tb=no --disable-warnings` — **259 passed, 1 skipped**

## Next Recommended Card

**AI-1214 — What-If Simulator**
