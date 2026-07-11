from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account
from app.reports.schemas import NetWorthAccountRow, NetWorthResponse
from app.services.accounting_service import AccountingService


async def generate_net_worth(
    db: AsyncSession,
    tenant_id: int,
    as_of_date: date,
    currency: str = "OMR",
) -> NetWorthResponse:
    """Build a net-worth summary as of the given date."""
    accounting = AccountingService(db, tenant_id)

    result = await db.execute(
        select(Account)
        .where(Account.tenant_id == tenant_id)
        .where(Account.account_type.in_(["Asset", "Liability"]))
        .order_by(Account.account_type, Account.code)
    )
    accounts = result.scalars().all()

    rows: List[NetWorthAccountRow] = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")

    for account in accounts:
        balance = await accounting.get_account_balance(
            account.id, None, as_of_date, exclude_reversed=False
        )
        rows.append(
            NetWorthAccountRow(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                account_type=account.account_type,
                amount=balance,
            )
        )
        if account.account_type == "Asset":
            total_assets += balance
        elif account.account_type == "Liability":
            total_liabilities += balance

    return NetWorthResponse(
        as_of_date=as_of_date,
        currency=currency,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=total_assets - total_liabilities,
        accounts=rows,
    )
