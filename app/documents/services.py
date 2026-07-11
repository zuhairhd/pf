"""Document management service layer."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.documents import ocr, storage
from app.models import Bill, Document, Goal, JournalEntry, Subscription
from app.schemas.document import DocumentCreate, DocumentUpdate


settings = get_settings()


_SUPPORTED_ENTITY_TYPES = {
    "transaction": JournalEntry,
    "bill": Bill,
    "subscription": Subscription,
    "goal": Goal,
}


class DocumentService:
    """Tenant-scoped document upload, storage, OCR, and linking service."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        user_id: Optional[int] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create_document(
        self,
        file: UploadFile,
        metadata: DocumentCreate,
    ) -> Document:
        """Validate, store, and record a new document."""
        stored = storage.save_upload(file, self.tenant_id, settings)

        document = Document(
            tenant_id=self.tenant_id,
            uploaded_by_user_id=self.user_id,
            filename=stored["filename_stored"],
            filename_stored=stored["filename_stored"],
            original_filename=stored["original_filename"],
            document_type=metadata.document_type or "other",
            category=metadata.category,
            file_size=stored["file_size"],
            mime_type=stored["mime_type"],
            storage_path=stored["storage_path"],
            checksum=stored["checksum"],
            status="uploaded",
            description=metadata.description,
            related_entity_type=metadata.related_entity_type,
            related_entity_id=metadata.related_entity_id,
        )

        if metadata.related_entity_type and metadata.related_entity_id is not None:
            await self._validate_related_entity(
                metadata.related_entity_type,
                metadata.related_entity_id,
            )

        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def list_documents(self) -> list[Document]:
        """Return documents visible to the current tenant."""
        result = await self.db.execute(
            select(Document)
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.status != "archived")
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_document(self, document_id: int) -> Document:
        """Fetch a single tenant document or raise 404."""
        result = await self.db.execute(
            select(Document)
            .where(Document.id == document_id)
            .where(Document.tenant_id == self.tenant_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    async def update_document(
        self,
        document_id: int,
        payload: DocumentUpdate,
    ) -> Document:
        """Update editable metadata for a document."""
        document = await self.get_document(document_id)
        data = payload.model_dump(exclude_unset=True)

        if "related_entity_type" in data or "related_entity_id" in data:
            entity_type = data.get("related_entity_type", document.related_entity_type)
            entity_id = data.get("related_entity_id", document.related_entity_id)
            if entity_type and entity_id is not None:
                await self._validate_related_entity(entity_type, entity_id)

        for field in (
            "document_type",
            "category",
            "description",
            "status",
            "related_entity_type",
            "related_entity_id",
        ):
            if field in data:
                setattr(document, field, data[field])

        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def archive_document(self, document_id: int) -> Document:
        """Mark a document as archived."""
        document = await self.get_document(document_id)
        document.status = "archived"
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def delete_document(self, document_id: int) -> None:
        """Delete a document record and its stored file."""
        document = await self.get_document(document_id)
        storage.delete_file(document.storage_path)
        await self.db.delete(document)
        await self.db.commit()

    async def get_file_path(self, document_id: int) -> str:
        """Return the absolute filesystem path for a document."""
        document = await self.get_document(document_id)
        return str(storage.resolve_storage_path(document.storage_path))

    async def run_ocr(self, document_id: int) -> Document:
        """Run OCR/text extraction on a document."""
        document = await self.get_document(document_id)
        path = storage.resolve_storage_path(document.storage_path)

        if not storage.is_path_within_tenant_dir(
            document.storage_path, self.tenant_id, settings
        ):
            document.ocr_status = "failed"
            document.ocr_error = "Stored file is outside the tenant upload directory"
            await self.db.commit()
            await self.db.refresh(document)
            return document

        if not path.exists():
            document.ocr_status = "failed"
            document.ocr_error = "Stored file not found"
            await self.db.commit()
            await self.db.refresh(document)
            return document

        document.ocr_status = "processing"
        document.status = "processing"
        await self.db.commit()

        try:
            content = path.read_bytes()
            result = ocr.OCRProcessor().process(content, document.mime_type, settings)
            document.ocr_text = result.text
            document.ocr_status = result.status
            document.ocr_confidence = result.confidence
            document.ocr_error = result.error
            if result.status == "processed":
                document.status = "processed"
            elif result.status == "failed":
                document.status = "failed"
            else:
                document.status = "uploaded"
        except Exception as exc:
            document.ocr_status = "failed"
            document.ocr_error = str(exc)
            document.status = "failed"

        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def link_document(
        self,
        document_id: int,
        entity_type: str,
        entity_id: int,
    ) -> Document:
        """Link a document to a tenant-owned entity."""
        document = await self.get_document(document_id)
        await self._validate_related_entity(entity_type, entity_id)
        document.related_entity_type = entity_type
        document.related_entity_id = entity_id
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def unlink_document(self, document_id: int) -> Document:
        """Remove a document's entity link."""
        document = await self.get_document(document_id)
        document.related_entity_type = None
        document.related_entity_id = None
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def _validate_related_entity(
        self,
        entity_type: str,
        entity_id: int,
    ) -> None:
        """Ensure the referenced entity exists in the same tenant."""
        model = _SUPPORTED_ENTITY_TYPES.get(entity_type)
        if model is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported entity type: {entity_type}",
            )

        result = await self.db.execute(
            select(model.id)
            .where(model.id == entity_id)
            .where(model.tenant_id == self.tenant_id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=404,
                detail=f"{entity_type} {entity_id} not found in tenant",
            )
