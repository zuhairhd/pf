from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.documents.services import DocumentService
from app.models import User
from app.schemas.document import (
    DocumentCreate,
    DocumentLinkRequest,
    DocumentResponse,
    DocumentUpdate,
    OCRResultResponse,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _to_response(document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        tenant_id=document.tenant_id,
        uploaded_by_user_id=document.uploaded_by_user_id,
        original_filename=document.original_filename,
        filename_stored=document.filename_stored,
        document_type=document.document_type.value
        if hasattr(document.document_type, "value")
        else document.document_type,
        category=document.category,
        file_size=document.file_size,
        mime_type=document.mime_type,
        storage_path=document.storage_path,
        checksum=document.checksum,
        status=document.status.value if hasattr(document.status, "value") else document.status,
        ocr_text=document.ocr_text,
        ocr_confidence=document.ocr_confidence,
        ocr_status=document.ocr_status,
        ocr_error=document.ocr_error,
        related_entity_type=document.related_entity_type,
        related_entity_id=document.related_entity_id,
        description=document.description,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get("/", response_model=list[DocumentResponse])
async def documents_list(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List documents for the current tenant."""
    service = DocumentService(db, user.organization_id, user.id)
    documents = await service.list_documents()
    return [_to_response(doc) for doc in documents]


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    category: str | None = Form(None),
    description: str | None = Form(None),
    related_entity_type: str | None = Form(None),
    related_entity_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Upload a document with optional metadata and linking."""
    service = DocumentService(db, user.organization_id, user.id)
    metadata = DocumentCreate(
        document_type=document_type,
        category=category,
        description=description,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    document = await service.create_document(file, metadata)
    return _to_response(document)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single document's metadata."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.get_document(document_id)
    return _to_response(document)


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Download a document's stored file."""
    service = DocumentService(db, user.organization_id, user.id)
    file_path = await service.get_file_path(document_id)
    return FileResponse(file_path)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update document metadata."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.update_document(document_id, payload)
    return _to_response(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Delete a document and its stored file."""
    service = DocumentService(db, user.organization_id, user.id)
    await service.delete_document(document_id)
    return None


@router.post("/{document_id}/archive", response_model=DocumentResponse)
async def archive_document(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Archive a document."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.archive_document(document_id)
    return _to_response(document)


def _to_ocr_response(document, preview_length: int = 500) -> OCRResultResponse:
    text = document.ocr_text
    preview = text[:preview_length] if text else None
    return OCRResultResponse(
        document_id=document.id,
        ocr_status=document.ocr_status,
        ocr_text=text,
        text_preview=preview,
        ocr_error=document.ocr_error,
        updated_at=document.updated_at,
    )


@router.post("/{document_id}/ocr", response_model=OCRResultResponse)
async def run_document_ocr(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Run OCR/text extraction on a document."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.run_ocr(document_id)
    return _to_ocr_response(document)


@router.post("/{document_id}/link", response_model=DocumentResponse)
async def link_document(
    document_id: int,
    payload: DocumentLinkRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Link a document to a tenant-owned entity."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.link_document(
        document_id,
        payload.related_entity_type,
        payload.related_entity_id,
    )
    return _to_response(document)


@router.post("/{document_id}/unlink", response_model=DocumentResponse)
async def unlink_document(
    document_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Remove a document's entity link."""
    service = DocumentService(db, user.organization_id, user.id)
    document = await service.unlink_document(document_id)
    return _to_response(document)
