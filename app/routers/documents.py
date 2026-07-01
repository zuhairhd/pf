from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import Document
from app.services.document_service import DocumentService
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def documents_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Documents list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Document).where(Document.tenant_id == tenant_id).order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    
    return templates.TemplateResponse("documents/list.html", {
        "request": request,
        "documents": documents,
    })


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "other",
    db: AsyncSession = Depends(get_db)
):
    """Upload a document."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = DocumentService(db, tenant_id)
    document = await service.upload_document(file, document_type)
    
    return document


@router.get("/{document_id}/download")
async def download_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """Download a document."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = DocumentService(db, tenant_id)
    file_path = await service.get_document_path(document_id)
    
    return FileResponse(file_path)
