from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    """Metadata supplied when uploading a document."""

    document_type: Optional[str] = Field(
        default="other",
        pattern="^(receipt|invoice|statement|tax_document|insurance|contract|other)$",
    )
    category: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=1000)
    related_entity_type: Optional[str] = Field(default=None, max_length=50)
    related_entity_id: Optional[int] = None


class DocumentUpdate(BaseModel):
    """Editable document metadata."""

    document_type: Optional[str] = Field(
        default=None,
        pattern="^(receipt|invoice|statement|tax_document|insurance|contract|other)$",
    )
    category: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = Field(
        default=None,
        pattern="^(uploaded|processing|processed|failed|archived)$",
    )
    related_entity_type: Optional[str] = Field(default=None, max_length=50)
    related_entity_id: Optional[int] = None


class DocumentLinkRequest(BaseModel):
    """Link a document to a tenant-owned entity."""

    related_entity_type: str = Field(..., max_length=50)
    related_entity_id: int = Field(..., ge=1)


class OCRResultResponse(BaseModel):
    """Result of an OCR/text extraction request."""

    document_id: int
    ocr_status: str
    ocr_text: Optional[str] = None
    text_preview: Optional[str] = None
    ocr_error: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Document record returned by the API."""

    id: int
    tenant_id: int
    uploaded_by_user_id: Optional[int] = None
    original_filename: str
    filename_stored: Optional[str] = None
    document_type: str
    category: Optional[str] = None
    file_size: int
    mime_type: str
    storage_path: str
    checksum: Optional[str] = None
    status: str
    ocr_text: Optional[str] = None
    ocr_confidence: Optional[Decimal] = None
    ocr_status: Optional[str] = None
    ocr_error: Optional[str] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
