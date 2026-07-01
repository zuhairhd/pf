from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
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


class Document(Base, TimestampMixin, TenantMixin):
    """An uploaded document."""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    document_type = Column(SQLEnum(DocumentType), default=DocumentType.OTHER, nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    mime_type = Column(String(100), nullable=False)
    storage_path = Column(String(500), nullable=False)
    
    # OCR
    ocr_text = Column(Text, nullable=True)
    ocr_confidence = Column(Numeric(5, 2), nullable=True)
    
    # AI parsing
    ai_parsed_data = Column(Text, nullable=True)  # JSON
    ai_linked_transaction_id = Column(Integer, nullable=True)
    
    description = Column(Text, nullable=True)
