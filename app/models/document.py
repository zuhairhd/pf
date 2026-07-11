from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class DocumentType(str, enum.Enum):
    RECEIPT = "receipt"
    INVOICE = "invoice"
    STATEMENT = "statement"
    TAX_DOCUMENT = "tax_document"
    INSURANCE = "insurance"
    CONTRACT = "contract"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    ARCHIVED = "archived"


class Document(Base, TimestampMixin, TenantMixin):
    """An uploaded document with OCR-ready metadata and optional entity links."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # legacy stored filename
    filename_stored = Column(String(255), nullable=True)
    original_filename = Column(String(255), nullable=False)
    document_type = Column(SQLEnum(DocumentType), default=DocumentType.OTHER, nullable=False)
    category = Column(String(50), nullable=True, index=True)
    file_size = Column(Integer, nullable=False)  # bytes
    mime_type = Column(String(100), nullable=False)
    storage_path = Column(String(500), nullable=False)
    checksum = Column(String(64), nullable=True, index=True)

    # Uploader
    uploaded_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    # Processing status
    status = Column(
        String(20), default=DocumentStatus.UPLOADED.value, nullable=False, index=True
    )

    # OCR
    ocr_text = Column(Text, nullable=True)
    ocr_confidence = Column(Numeric(5, 2), nullable=True)
    ocr_status = Column(String(20), nullable=True)
    ocr_error = Column(Text, nullable=True)

    # AI parsing (legacy/optional)
    ai_parsed_data = Column(Text, nullable=True)  # JSON
    ai_linked_transaction_id = Column(Integer, nullable=True)

    # Generic entity link
    related_entity_type = Column(String(50), nullable=True, index=True)
    related_entity_id = Column(Integer, nullable=True, index=True)

    description = Column(Text, nullable=True)

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by_user_id])

    __table_args__ = (
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_tenant_uploader", "tenant_id", "uploaded_by_user_id"),
        Index(
            "ix_documents_tenant_related_entity",
            "tenant_id",
            "related_entity_type",
            "related_entity_id",
        ),
        {"sqlite_autoincrement": True},
    )
