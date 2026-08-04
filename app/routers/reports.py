from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User
from app.reports.schemas import (
    BalanceSheetResponse,
    CashFlowResponse,
    ExpenseAnalysisResponse,
    IncomeStatementResponse,
    NetWorthResponse,
)
from app.reports.services import ReportService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_date_param(value: date, name: str) -> date:
    if value is None:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    return value


def _currency_for(user: User) -> str:
    return user.currency or "OMR"


@router.get("/income-statement", response_model=IncomeStatementResponse)
async def income_statement(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the tenant income statement for the requested period."""
    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be on or before end_date"
        )

    service = ReportService(db, user.organization_id, _currency_for(user))
    return await service.income_statement(start_date, end_date)


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def balance_sheet(
    as_of_date: date = Query(...),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the tenant balance sheet as of the requested date."""
    service = ReportService(db, user.organization_id, _currency_for(user))
    return await service.balance_sheet(as_of_date)


@router.get("/cash-flow", response_model=CashFlowResponse)
async def cash_flow(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the tenant cash-flow summary for the requested period."""
    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be on or before end_date"
        )

    service = ReportService(db, user.organization_id, _currency_for(user))
    return await service.cash_flow(start_date, end_date)


@router.get("/net-worth", response_model=NetWorthResponse)
async def net_worth(
    as_of_date: date = Query(...),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the tenant net-worth summary as of the requested date."""
    service = ReportService(db, user.organization_id, _currency_for(user))
    return await service.net_worth(as_of_date)


@router.get("/expense-analysis", response_model=ExpenseAnalysisResponse)
async def expense_analysis(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the tenant expense analysis for the requested period."""
    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be on or before end_date"
        )

    service = ReportService(db, user.organization_id, _currency_for(user))
    return await service.expense_analysis(start_date, end_date)


# ---------------------------------------------------------------------------
# Report Center UI (REP-2001)
#
# Server-rendered/HTMX views on top of the JSON endpoints above. No report
# calculation logic lives here — every route below only ever calls the same
# ReportService used by the JSON API. All routes are GET-only and never
# create, update, or delete any financial record.
# ---------------------------------------------------------------------------

REPORT_TABS = [
    {"key": "income-statement", "label": "Income Statement", "icon": "bi-graph-up-arrow"},
    {"key": "balance-sheet", "label": "Balance Sheet", "icon": "bi-bank"},
    {"key": "cash-flow", "label": "Cash Flow", "icon": "bi-arrow-left-right"},
    {"key": "net-worth", "label": "Net Worth", "icon": "bi-piggy-bank"},
    {"key": "expense-analysis", "label": "Expense Analysis", "icon": "bi-pie-chart"},
]


def _default_period() -> tuple[date, date]:
    """Default period for period reports: first day of the current month through today."""
    today = date.today()
    return today.replace(day=1), today


def _default_as_of() -> date:
    """Default as-of date for balance-sheet/net-worth: today."""
    return date.today()


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def reports_center(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Report Center landing page: navigation cards, filters, and the
    Income Statement pre-loaded as the default report panel."""
    default_start, default_end = _default_period()
    report = None
    error = None
    try:
        service = ReportService(db, user.organization_id, _currency_for(user))
        report = await service.income_statement(default_start, default_end)
    except Exception:
        error = "This report is temporarily unavailable. Your data is safe and unchanged."

    return templates.TemplateResponse(
        request,
        "reports/index.html",
        {
            "report_tabs": REPORT_TABS,
            "active_report": "income-statement",
            "start_date": default_start,
            "end_date": default_end,
            "as_of_date": _default_as_of(),
            "report": report,
            "error": error,
        },
    )


@router.get("/partials/income-statement", response_class=HTMLResponse)
async def income_statement_partial(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: income statement for the requested (or default) period."""
    default_start, default_end = _default_period()
    start_date = start_date or default_start
    end_date = end_date or default_end

    report = None
    error = None
    if start_date > end_date:
        error = "Start date must be on or before end date."
    else:
        service = ReportService(db, user.organization_id, _currency_for(user))
        report = await service.income_statement(start_date, end_date)

    return templates.TemplateResponse(
        request,
        "reports/partials/income_statement.html",
        {
            "active_report": "income-statement",
            "start_date": start_date,
            "end_date": end_date,
            "report": report,
            "error": error,
        },
        status_code=400 if error else 200,
    )


@router.get("/partials/balance-sheet", response_class=HTMLResponse)
async def balance_sheet_partial(
    request: Request,
    as_of_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: balance sheet as of the requested (or default) date."""
    as_of_date = as_of_date or _default_as_of()

    service = ReportService(db, user.organization_id, _currency_for(user))
    report = await service.balance_sheet(as_of_date)

    return templates.TemplateResponse(
        request,
        "reports/partials/balance_sheet.html",
        {
            "active_report": "balance-sheet",
            "as_of_date": as_of_date,
            "report": report,
            "error": None,
        },
    )


@router.get("/partials/cash-flow", response_class=HTMLResponse)
async def cash_flow_partial(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: cash flow summary for the requested (or default) period."""
    default_start, default_end = _default_period()
    start_date = start_date or default_start
    end_date = end_date or default_end

    report = None
    error = None
    if start_date > end_date:
        error = "Start date must be on or before end date."
    else:
        service = ReportService(db, user.organization_id, _currency_for(user))
        report = await service.cash_flow(start_date, end_date)

    return templates.TemplateResponse(
        request,
        "reports/partials/cash_flow.html",
        {
            "active_report": "cash-flow",
            "start_date": start_date,
            "end_date": end_date,
            "report": report,
            "error": error,
        },
        status_code=400 if error else 200,
    )


@router.get("/partials/net-worth", response_class=HTMLResponse)
async def net_worth_partial(
    request: Request,
    as_of_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: net worth summary as of the requested (or default) date."""
    as_of_date = as_of_date or _default_as_of()

    service = ReportService(db, user.organization_id, _currency_for(user))
    report = await service.net_worth(as_of_date)

    return templates.TemplateResponse(
        request,
        "reports/partials/net_worth.html",
        {
            "active_report": "net-worth",
            "as_of_date": as_of_date,
            "report": report,
            "error": None,
        },
    )


@router.get("/partials/expense-analysis", response_class=HTMLResponse)
async def expense_analysis_partial(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial: expense analysis for the requested (or default) period."""
    default_start, default_end = _default_period()
    start_date = start_date or default_start
    end_date = end_date or default_end

    report = None
    error = None
    if start_date > end_date:
        error = "Start date must be on or before end date."
    else:
        service = ReportService(db, user.organization_id, _currency_for(user))
        report = await service.expense_analysis(start_date, end_date)

    return templates.TemplateResponse(
        request,
        "reports/partials/expense_analysis.html",
        {
            "active_report": "expense-analysis",
            "start_date": start_date,
            "end_date": end_date,
            "report": report,
            "error": error,
        },
        status_code=400 if error else 200,
    )
