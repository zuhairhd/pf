"""API routes for CSV imports."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    get_db_with_tenant_context,
    require_active_user,
    require_tenant_member,
)
from app.imports.models import ImportJob, ImportedRow
from app.imports.schemas import (
    CSVUploadRequest,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
    ImportRowFilter,
    ParsedRow,
    ImportJobSummary,
    SMSParseRequest,
)
from app.imports.services import ImportService, ImportServiceError
from app.models import User


router = APIRouter(tags=["Imports"])


def _to_summary(job: ImportJob) -> dict:
    return {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "user_id": job.user_id,
        "import_type": job.import_type,
        "status": job.status,
        "original_filename": job.original_filename,
        "file_hash": job.file_hash,
        "mapping": job.mapping,
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "duplicate_rows": job.duplicate_rows,
        "imported_rows": job.imported_rows,
        "errors": job.errors,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _to_parsed_row(row: ImportedRow) -> ParsedRow:
    return ParsedRow(
        row_number=row.row_number,
        raw_data=row.raw_data or {},
        parsed_data=row.parsed_data or {},
        validation_errors=row.validation_errors or [],
        status=row.status,
    )


@router.post("/csv/upload", response_model=ImportPreviewResponse)
async def upload_csv(
    payload: CSVUploadRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Upload and preview a CSV file.

    The file content is passed as a base64/utf-8 string for simplicity in this
    first version. The parser auto-detects columns and returns a preview of all
    rows with validation status.
    """
    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_job(
            user=user,
            original_filename=payload.original_filename,
            file_content=payload.file_content,
            mapping_hint=payload.mapping,
        )
    except ImportServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    rows = await service.get_job_rows(job.id, limit=1000)
    return ImportPreviewResponse(
        job_id=job.id,
        summary=_to_summary(job),
        rows=[_to_parsed_row(r) for r in rows],
    )


@router.post("/sms/parse", response_model=ImportPreviewResponse)
async def parse_sms(
    payload: SMSParseRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Parse pasted SMS bank alerts and return a preview import job."""
    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_sms_job(
            user=user,
            original_filename=payload.original_filename,
            sms_text=payload.sms_text,
        )
    except ImportServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    rows = await service.get_job_rows(job.id, limit=1000)
    return ImportPreviewResponse(
        job_id=job.id,
        summary=_to_summary(job),
        rows=[_to_parsed_row(r) for r in rows],
    )


@router.get("/{job_id}", response_model=ImportJobSummary)
async def get_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the summary for a single import job."""
    service = ImportService(db, tenant_id=user.organization_id)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return _to_summary(job)


@router.get("/{job_id}/rows")
async def get_import_job_rows(
    job_id: int,
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the parsed rows for an import job."""
    service = ImportService(db, tenant_id=user.organization_id)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    rows = await service.get_job_rows(job_id, status=status, limit=limit, offset=offset)
    return {
        "job_id": job_id,
        "rows": [_to_parsed_row(r) for r in rows],
        "count": len(rows),
    }


@router.post("/{job_id}/confirm", response_model=ImportConfirmResponse)
async def confirm_import_job(
    job_id: int,
    payload: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Confirm a previewed import and create journal entries for valid rows."""
    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.confirm_job(job_id, payload)
    except ImportServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return ImportConfirmResponse(
        job_id=job.id,
        imported_rows=job.imported_rows,
        skipped_rows=job.total_rows - job.imported_rows,
        status=job.status,
    )


@router.post("/{job_id}/cancel")
async def cancel_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel an import job that has not been completed."""
    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.cancel_job(job_id)
    except ImportServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return {"job_id": job.id, "status": job.status}
