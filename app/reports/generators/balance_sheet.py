from datetime import date
from decimal import Decimal
from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.schemas import BalanceSheetResponse, ReportAccountRow
from app.services.accounting_service import AccountingService


async def generate_balance_sheet(
    db: AsyncSession,
    tenant_id: int,
    as_of_date: date,
    currency: str = "OMR",
) -> BalanceSheetResponse:
    """Build a balance sheet as of the given date, excluding reversed originals."""
    accounting = AccountingService(db, tenant_id)
    data = await accounting.get_balance_sheet(
        as_of_date=as_of_date, exclude_reversed=False
    )

    asset_accounts = [
        ReportAccountRow(
            account_id=row["account"].id,
            account_code=row["account"].code,
            account_name=row["account"].name,
            amount=row["balance"],
        )
        for row in data["asset_rows"]
    ]

    liability_accounts = [
        ReportAccountRow(
            account_id=row["account"].id,
            account_code=row["account"].code,
            account_name=row["account"].name,
            amount=row["balance"],
        )
        for row in data["liability_rows"]
    ]

    equity_accounts = [
        ReportAccountRow(
            account_id=row["account"].id,
            account_code=row["account"].code,
            account_name=row["account"].name,
            amount=row["balance"],
        )
        for row in data["equity_rows"]
    ]

    balance_check = (
        data["total_assets"]
        == data["total_liabilities"] + data["total_equity"]
    )

    return BalanceSheetResponse(
        as_of_date=as_of_date,
        currency=currency,
        assets_total=data["total_assets"],
        liabilities_total=data["total_liabilities"],
        equity_total=data["total_equity"],
        net_worth=data["net_worth"],
        balance_check=balance_check,
        asset_accounts=asset_accounts,
        liability_accounts=liability_accounts,
        equity_accounts=equity_accounts,
    )
