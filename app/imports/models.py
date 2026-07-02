"""Data import models.

ImportJob and ImportedRow are tenant-scoped so RLS policies can filter them by
tenant context. ImportedRow carries a direct tenant_id for clarity and
performance, even though it also belongs to an ImportJob.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.database import Base
from app.models.mixins import TimestampMixin


class ImportJob(Base, TimestampMixin):
    """A user-initiated data import job."""

    __tablename__ = "import_jobs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    import_type = Column(String(20), nullable=False, default="csv")
    status = Column(String(20), nullable=False, default="uploaded")

    original_filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)

    # Column mapping from CSV headers to app fields.
    mapping = Column(JSONB, nullable=False, default=dict)

    total_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    duplicate_rows = Column(Integer, nullable=False, default=0)
    imported_rows = Column(Integer, nullable=False, default=0)

    # General job-level errors and metadata.
    errors = Column(JSONB, nullable=False, default=list)

    completed_at = Column(DateTime, nullable=True)

    user = relationship("User")
    rows = relationship(
        "ImportedRow",
        back_populates="import_job",
        cascade="all, delete-orphan",
        order_by="ImportedRow.row_number",
    )


class ImportedRow(Base, TimestampMixin):
    """A single row parsed from an import file."""

    __tablename__ = "imported_rows"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    import_job_id = Column(
        Integer, ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_number = Column(Integer, nullable=False)

    # Raw values straight from the CSV.
    raw_data = Column(JSONB, nullable=False, default=dict)

    # Normalized values after parsing (date, amount, etc.).
    parsed_data = Column(JSONB, nullable=False, default=dict)

    # Row-level validation errors.
    validation_errors = Column(JSONB, nullable=False, default=list)

    # Duplicate detection reference.
    duplicate_key = Column(String(255), nullable=True, index=True)
    duplicate_of_row_id = Column(Integer, ForeignKey("imported_rows.id"), nullable=True)

    status = Column(String(20), nullable=False, default="valid")

    import_job = relationship("ImportJob", back_populates="rows")

    __table_args__ = (
        # Ensure row numbers are unique within a job.
        {"sqlite_autoincrement": True},
    )
