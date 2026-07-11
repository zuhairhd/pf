from datetime import date
from decimal import Decimal
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.schemas import IncomeStatementResponse, ReportAccountRow
from app.services.accounting_service import AccountingService


async def generate_income_statement(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    currency: str = "OMR",
) -> IncomeStatementResponse:
    """Build an income statement for the tenant, excluding reversed originals."""
    accounting = AccountingService(db, tenant_id)
    data = await accounting.get_income_statement(
        start_date, end_date, exclude_reversed=False
    )

    income_accounts = [
        ReportAccountRow(
            account_id=row["account"].id,
            account_code=row["account"].code,
            account_name=row["account"].name,
            amount=row["balance"],
        )
        for row in data["income_rows"]
    ]

    expense_accounts = [
        ReportAccountRow(
            account_id=row["account"].id,
            account_code=row["account"].code,
            account_name=row["account"].name,
            amount=row["balance"],
        )
        for row in data["expense_rows"]
    ]

    return IncomeStatementResponse(
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        income_total=data["total_income"],
        expense_total=data["total_expenses"],
        net_income=data["surplus"],
        income_accounts=income_accounts,
        expense_accounts=expense_accounts,
    )
