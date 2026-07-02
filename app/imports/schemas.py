"""Pydantic schemas for the imports module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class ColumnMapping(BaseModel):
    """Maps a CSV column to an application field."""

    date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[str] = None
    debit: Optional[str] = None
    credit: Optional[str] = None
    transaction_type: Optional[str] = None
    account: Optional[str] = None
    category: Optional[str] = None
    reference: Optional[str] = None
    currency: Optional[str] = None
    balance: Optional[str] = None


class CSVUploadRequest(BaseModel):
    """Request body for uploading and parsing a CSV file."""

    original_filename: str = Field(..., min_length=1, max_length=255)
    file_content: str = Field(..., min_length=1)
    mapping: ColumnMapping = Field(default_factory=ColumnMapping)
    currency: str = Field(default="OMR", max_length=3)


class ParsedRow(BaseModel):
    """A single parsed row returned in previews."""

    row_number: int
    raw_data: dict[str, Any]
    parsed_data: dict[str, Any]
    validation_errors: list[str]
    status: str


class ImportJobSummary(BaseModel):
    """Summary of an import job."""

    id: int
    tenant_id: int
    user_id: int
    import_type: str
    status: str
    original_filename: str
    file_hash: str
    mapping: dict[str, Any]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    imported_rows: int
    errors: list[str]
    created_at: str
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True


class ImportPreviewResponse(BaseModel):
    """Response returned immediately after CSV upload/preview."""

    job_id: int
    summary: ImportJobSummary
    rows: list[ParsedRow]


class ImportConfirmRequest(BaseModel):
    """Request body for confirming an import and creating transactions."""

    bank_account_id: int
    default_income_account_id: Optional[int] = None
    default_expense_account_id: Optional[int] = None
    import_duplicates: bool = False


class ImportConfirmResponse(BaseModel):
    """Response returned after confirming an import."""

    job_id: int
    imported_rows: int
    skipped_rows: int
    status: str


class ImportRowFilter(BaseModel):
    """Query parameters for listing import rows."""

    status: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
