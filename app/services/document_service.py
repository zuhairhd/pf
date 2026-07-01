from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
import os
import shutil

from app.models import Document
from app.config import get_settings

settings = get_settings()


class DocumentService:
    """Document upload, storage, and OCR service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def upload_document(self, file, document_type: str) -> Document:
        """Upload and store a document."""
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.tenant_id}_{timestamp}_{file.filename}"
        file_path = os.path.join(self.upload_dir, filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create document record
        document = Document(
            tenant_id=self.tenant_id,
            filename=filename,
            original_filename=file.filename,
            document_type=document_type,
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            storage_path=file_path,
        )
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document
    
    async def get_document_path(self, document_id: int) -> str:
        """Get the file path for a document."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id)
            .where(Document.tenant_id == self.tenant_id)
        )
        document = result.scalar_one_or_none()
        if not document:
            raise ValueError("Document not found")
        return document.storage_path
    
    async def delete_document(self, document_id: int) -> None:
        """Delete a document and its file."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id)
            .where(Document.tenant_id == self.tenant_id)
        )
        document = result.scalar_one_or_none()
        if not document:
            return
        
        # Delete file
        if os.path.exists(document.storage_path):
            os.remove(document.storage_path)
        
        # Delete record
        await self.db.delete(document)
        await self.db.commit()
    
    async def run_ocr(self, document_id: int) -> Optional[str]:
        """Run OCR on a document (placeholder for future implementation)."""
        # TODO: Implement OCR using pytesseract or cloud OCR
        return None
