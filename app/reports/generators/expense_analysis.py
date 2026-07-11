from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.reports.schemas import ExpenseAccountRow, ExpenseAnalysisResponse
from app.services.accounting_service import AccountingService


def _safe_percent(amount: Decimal, total: Decimal) -> Decimal:
    """Return amount / total as a percentage, or zero when total is zero."""
    if total == 0:
        return Decimal("0")
    return (amount / total) * Decimal("100")


async def generate_expense_analysis(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    currency: str = "OMR",
    top_n: int = 10,
) -> ExpenseAnalysisResponse:
    """Build an expense analysis report for the period."""
    accounting = AccountingService(db, tenant_id)

    result = await db.execute(
        select(Account)
        .where(Account.tenant_id == tenant_id)
        .where(Account.account_type == "Expense")
        .order_by(Account.code)
    )
    expense_accounts = result.scalars().all()

    rows: List[ExpenseAccountRow] = []
    total_expenses = Decimal("0")

    for account in expense_accounts:
        amount = await accounting.get_account_balance(
            account.id, start_date, end_date, exclude_reversed=False
        )
        rows.append(
            ExpenseAccountRow(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                amount=amount,
                percent_of_total=Decimal("0"),
            )
        )
        total_expenses += amount

    # Compute percentages now that the total is known.
    for row in rows:
        row.percent_of_total = _safe_percent(row.amount, total_expenses)

    sorted_rows = sorted(rows, key=lambda r: r.amount, reverse=True)
    return ExpenseAnalysisResponse(
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        total_expenses=total_expenses,
        expenses_by_account=sorted(rows, key=lambda r: r.account_code),
        top_expense_accounts=sorted_rows[:top_n],
    )
