from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
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
