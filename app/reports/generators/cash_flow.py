from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, JournalEntry, JournalLine
from app.reports.schemas import CashFlowAccountRow, CashFlowResponse


def _is_cash_account(account: Account) -> bool:
    """Return True for bank/cash/wallet asset accounts."""
    return account.is_bank_account or account.is_cash_account


async def generate_cash_flow(
    db: AsyncSession,
    tenant_id: int,
    start_date: date,
    end_date: date,
    currency: str = "OMR",
) -> CashFlowResponse:
    """Build a cash-flow summary for the period using cash/bank asset accounts.

    Inflow is the total of debits to cash accounts (money entering) and outflow
    is the total of credits (money leaving). Both the original entry and any
    reversing entry are included so they offset each other.
    """
    result = await db.execute(
        select(Account)
        .where(Account.tenant_id == tenant_id)
        .where(Account.account_type == "Asset")
        .order_by(Account.code)
    )
    asset_accounts = list(result.scalars().all())

    cash_accounts = [a for a in asset_accounts if _is_cash_account(a)]
    if not cash_accounts:
        # Fallback: treat all asset accounts as a cash proxy when no accounts
        # are explicitly classified as bank/cash.
        cash_accounts = asset_accounts

    rows: List[CashFlowAccountRow] = []
    total_inflow = Decimal("0")
    total_outflow = Decimal("0")

    for account in cash_accounts:
        sums = await db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            )
            .join(JournalEntry)
            .where(JournalLine.account_id == account.id)
            .where(JournalLine.tenant_id == tenant_id)
            .where(JournalEntry.date >= start_date)
            .where(JournalEntry.date <= end_date)
        )
        debit_sum, credit_sum = sums.one()

        rows.append(
            CashFlowAccountRow(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                inflow=debit_sum,
                outflow=credit_sum,
                net=debit_sum - credit_sum,
            )
        )
        total_inflow += debit_sum
        total_outflow += credit_sum

    return CashFlowResponse(
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        cash_inflow=total_inflow,
        cash_outflow=total_outflow,
        net_cash_flow=total_inflow - total_outflow,
        by_account=rows,
    )
