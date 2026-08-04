"""API routes for CSV imports."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import (
    get_db_with_tenant_context,
    require_active_user,
    require_tenant_member,
)
from app.imports.models import ImportJob, ImportedRow
from app.imports.schemas import (
    ColumnMapping,
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
from app.services.family_account_access_service import FamilyAccountAccessService


router = APIRouter(tags=["Imports"])
templates = Jinja2Templates(directory="app/templates")


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


@router.post("/excel/upload", response_model=ImportPreviewResponse)
async def upload_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
    default_account_id: Optional[int] = Form(None),
    default_currency: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Upload and preview an Excel (.xlsx) workbook.

    Only the .xlsx format is supported (legacy .xls is not). The file is read
    entirely in memory with openpyxl in read-only, data-only mode and is never
    written to disk -- formulas and macros are never executed, only cached
    cell values are read.
    """
    original_name = Path(file.filename or "").name.strip()
    if not original_name.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Only .xlsx Excel files are supported. "
                "Legacy .xls workbooks are not supported."
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    settings = get_settings()
    max_size = settings.DOCUMENT_MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.DOCUMENT_MAX_UPLOAD_MB} MB",
        )

    mapping_hint = ColumnMapping()
    if mapping:
        try:
            mapping_hint = ColumnMapping.model_validate_json(mapping)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid mapping JSON") from exc

    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_excel_job(
            user=user,
            original_filename=original_name or "workbook.xlsx",
            file_content=content,
            sheet_name=sheet_name or None,
            mapping_hint=mapping_hint,
            default_account_id=default_account_id,
            default_currency=default_currency,
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
        job = await service.confirm_job(job_id, payload, user)
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


# ---------------------------------------------------------------------------
# Import Center UI (IMP-703)
#
# Server-rendered/HTMX views on top of the JSON endpoints above. No parser,
# validation, duplicate-detection, or confirm/posting logic lives here --
# every route below only ever calls the same ImportService methods used by
# the JSON API (create_job / create_sms_job / create_excel_job / get_job /
# get_job_rows / confirm_job / cancel_job / list_jobs). All non-upload GET
# routes are read-only; only the confirm routes ever create journal entries,
# and they do so through the unchanged AccountingService-backed confirm_job.
# ---------------------------------------------------------------------------


def _parse_mapping_hint(mapping_text: Optional[str]) -> tuple[ColumnMapping, Optional[str]]:
    """Parse an optional JSON mapping string into a ColumnMapping.

    Returns (mapping, error_message). On invalid JSON, mapping is the default
    (empty) ColumnMapping and error_message describes the problem safely.
    """
    if not mapping_text or not mapping_text.strip():
        return ColumnMapping(), None
    try:
        return ColumnMapping.model_validate_json(mapping_text), None
    except ValueError:
        return ColumnMapping(), "Invalid mapping JSON. Please check the format and try again."


async def _account_options(db: AsyncSession, user: User) -> dict[str, list]:
    """Return account options visible/usable by the current user, grouped by type.

    Reuses FamilyAccountAccessService.list_visible_accounts() unchanged -- only
    accounts the user is already allowed to see are offered, so inaccessible
    private accounts and cross-tenant accounts never appear in any import form.
    """
    access = FamilyAccountAccessService(db, user.organization_id, user)
    visible_accounts = await access.list_visible_accounts()
    return {
        "all": visible_accounts,
        "bank": [a for a in visible_accounts if a.account_type == "Asset"],
        "income": [a for a in visible_accounts if a.account_type == "Income"],
        "expense": [a for a in visible_accounts if a.account_type == "Expense"],
    }


async def _render_preview(
    request: Request,
    db: AsyncSession,
    user: User,
    job_id: int,
    *,
    confirm_error: Optional[str] = None,
    cancel_error: Optional[str] = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the shared import job preview/confirm/cancel partial.

    Read-only: fetches the job, its rows, and account options via the same
    ImportService/FamilyAccountAccessService methods used elsewhere; never
    creates or modifies any record.
    """
    service = ImportService(db, tenant_id=user.organization_id)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    rows = await service.get_job_rows(job_id, limit=200)
    options = await _account_options(db, user)

    return templates.TemplateResponse(
        request,
        "imports/partials/preview.html",
        {
            "job": _to_summary(job),
            "rows": [_to_parsed_row(r) for r in rows],
            "bank_accounts": options["bank"],
            "income_accounts": options["income"],
            "expense_accounts": options["expense"],
            "confirm_error": confirm_error,
            "cancel_error": cancel_error,
        },
        status_code=status_code,
    )


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def import_center(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Import Center: method cards, upload workspace, and recent import history."""
    service = ImportService(db, tenant_id=user.organization_id)
    jobs = await service.list_jobs(limit=20)
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {"jobs": [_to_summary(j) for j in jobs]},
    )


@router.get("/partials/csv-form", response_class=HTMLResponse)
async def csv_form_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: CSV upload form (no side effects)."""
    return templates.TemplateResponse(request, "imports/partials/csv_form.html", {})


@router.get("/partials/excel-form", response_class=HTMLResponse)
async def excel_form_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: Excel upload form (no side effects)."""
    options = await _account_options(db, user)
    return templates.TemplateResponse(
        request, "imports/partials/excel_form.html", {"account_options": options["all"]}
    )


@router.get("/partials/sms-form", response_class=HTMLResponse)
async def sms_form_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: SMS paste form (no side effects)."""
    return templates.TemplateResponse(request, "imports/partials/sms_form.html", {})


@router.post("/ui/csv", response_class=HTMLResponse)
async def upload_csv_ui(
    request: Request,
    file: UploadFile = File(...),
    mapping: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Browser-friendly CSV upload.

    Reads the uploaded file as text and calls the exact same
    ImportService.create_job() used by POST /imports/csv/upload -- the CSV
    parser is never re-implemented here.
    """
    mapping_hint, mapping_error = _parse_mapping_hint(mapping)
    if mapping_error:
        return templates.TemplateResponse(
            request,
            "imports/partials/csv_form.html",
            {"form_error": mapping_error},
            status_code=400,
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        return templates.TemplateResponse(
            request,
            "imports/partials/csv_form.html",
            {"form_error": "Uploaded file is empty."},
            status_code=400,
        )

    try:
        file_content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return templates.TemplateResponse(
            request,
            "imports/partials/csv_form.html",
            {"form_error": "Could not read this file as text. Please upload a CSV text file."},
            status_code=400,
        )

    original_name = Path(file.filename or "import.csv").name.strip() or "import.csv"
    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_job(
            user=user,
            original_filename=original_name,
            file_content=file_content,
            mapping_hint=mapping_hint,
        )
    except ImportServiceError as exc:
        return templates.TemplateResponse(
            request,
            "imports/partials/csv_form.html",
            {"form_error": exc.message},
            status_code=400,
        )

    return await _render_preview(request, db, user, job.id)


@router.post("/ui/excel", response_class=HTMLResponse)
async def upload_excel_ui(
    request: Request,
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
    default_account_id: Optional[int] = Form(None),
    default_currency: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Browser-friendly Excel upload.

    Reuses the exact same ImportService.create_excel_job() used by
    POST /imports/excel/upload -- the Excel parser is never re-implemented
    here, and only .xlsx is accepted.
    """

    async def _form_error(message: str, status_code: int = 400) -> HTMLResponse:
        options = await _account_options(db, user)
        return templates.TemplateResponse(
            request,
            "imports/partials/excel_form.html",
            {"form_error": message, "account_options": options["all"]},
            status_code=status_code,
        )

    original_name = Path(file.filename or "").name.strip()
    if not original_name.lower().endswith(".xlsx"):
        return await _form_error(
            "Only .xlsx Excel files are supported. Legacy .xls workbooks are not supported."
        )

    content = await file.read()
    if not content:
        return await _form_error("Uploaded file is empty.")

    settings = get_settings()
    max_size = settings.DOCUMENT_MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_size:
        return await _form_error(
            f"File exceeds maximum size of {settings.DOCUMENT_MAX_UPLOAD_MB} MB.",
            status_code=413,
        )

    mapping_hint, mapping_error = _parse_mapping_hint(mapping)
    if mapping_error:
        return await _form_error(mapping_error)

    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_excel_job(
            user=user,
            original_filename=original_name or "workbook.xlsx",
            file_content=content,
            sheet_name=sheet_name or None,
            mapping_hint=mapping_hint,
            default_account_id=default_account_id,
            default_currency=default_currency,
        )
    except ImportServiceError as exc:
        return await _form_error(exc.message)

    return await _render_preview(request, db, user, job.id)


@router.post("/ui/sms", response_class=HTMLResponse)
async def parse_sms_ui(
    request: Request,
    sms_text: str = Form(...),
    original_filename: str = Form("sms_import.txt"),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Browser-friendly SMS paste.

    Reuses the exact same ImportService.create_sms_job() used by
    POST /imports/sms/parse -- the SMS parser is never re-implemented here.
    """
    if not sms_text.strip():
        return templates.TemplateResponse(
            request,
            "imports/partials/sms_form.html",
            {"form_error": "Please paste at least one SMS message."},
            status_code=400,
        )

    service = ImportService(db, tenant_id=user.organization_id)
    try:
        job = await service.create_sms_job(
            user=user,
            original_filename=original_filename or "sms_import.txt",
            sms_text=sms_text,
        )
    except ImportServiceError as exc:
        return templates.TemplateResponse(
            request,
            "imports/partials/sms_form.html",
            {"form_error": exc.message},
            status_code=400,
        )

    return await _render_preview(request, db, user, job.id)


@router.get("/partials/{job_id}/preview", response_class=HTMLResponse)
async def import_preview_partial(
    request: Request,
    job_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: import job summary, rows, and confirm/cancel controls."""
    return await _render_preview(request, db, user, job_id)


@router.get("/ui/{job_id}/preview", response_class=HTMLResponse)
async def import_preview_page(
    request: Request,
    job_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Full-page, bookmarkable import preview.

    The page itself only checks the job exists (tenant-scoped, read-only) and
    then lazily loads the same preview partial used everywhere else via HTMX.
    """
    service = ImportService(db, tenant_id=user.organization_id)
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    return templates.TemplateResponse(
        request, "imports/preview_page.html", {"job_id": job_id}
    )


@router.post("/ui/{job_id}/confirm", response_class=HTMLResponse)
async def confirm_import_ui(
    request: Request,
    job_id: int,
    bank_account_id: int = Form(...),
    default_income_account_id: Optional[int] = Form(None),
    default_expense_account_id: Optional[int] = Form(None),
    import_duplicates: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Browser-friendly confirm.

    Reuses the exact same ImportService.confirm_job() used by
    POST /imports/{job_id}/confirm, which posts through the unchanged
    AccountingService and account-visibility checks -- no posting logic is
    duplicated here.
    """
    service = ImportService(db, tenant_id=user.organization_id)
    payload = ImportConfirmRequest(
        bank_account_id=bank_account_id,
        default_income_account_id=default_income_account_id,
        default_expense_account_id=default_expense_account_id,
        import_duplicates=bool(import_duplicates),
    )

    confirm_error: Optional[str] = None
    try:
        await service.confirm_job(job_id, payload, user)
    except ImportServiceError as exc:
        confirm_error = exc.message

    return await _render_preview(
        request,
        db,
        user,
        job_id,
        confirm_error=confirm_error,
        status_code=400 if confirm_error else 200,
    )


@router.post("/ui/{job_id}/cancel", response_class=HTMLResponse)
async def cancel_import_ui(
    request: Request,
    job_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Browser-friendly cancel.

    Reuses the exact same ImportService.cancel_job() used by
    POST /imports/{job_id}/cancel.
    """
    service = ImportService(db, tenant_id=user.organization_id)
    cancel_error: Optional[str] = None
    try:
        await service.cancel_job(job_id)
    except ImportServiceError as exc:
        cancel_error = exc.message

    return await _render_preview(
        request,
        db,
        user,
        job_id,
        cancel_error=cancel_error,
        status_code=400 if cancel_error else 200,
    )
