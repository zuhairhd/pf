"""Background OCR task stub.

This module provides a Celery task entry point for document OCR. A full
implementation would create a sync database session, set the RLS tenant
context, and call ``DocumentService.run_ocr``. Celery workers are not yet
fully wired in this environment, so the task is intentionally a stub that
logs the request and returns a placeholder result.
"""

from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def process_document_ocr_task(self, document_id: int, tenant_id: int) -> dict:
    """Stub background task for processing document OCR.

    Args:
        document_id: The primary key of the document to process.
        tenant_id: The tenant that owns the document.

    Returns:
        A placeholder result dict. Real implementation should run the OCR
        pipeline inside a sync DB session with proper tenant context.
    """
    return {
        "document_id": document_id,
        "tenant_id": tenant_id,
        "status": "not_implemented",
        "message": "Background OCR processing is not wired in this environment.",
    }
