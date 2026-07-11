from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.reports import generators
from app.reports.schemas import (
    BalanceSheetResponse,
    CashFlowResponse,
    ExpenseAnalysisResponse,
    IncomeStatementResponse,
    NetWorthResponse,
)


class ReportService:
    """Tenant-scoped financial report service."""

    def __init__(self, db: AsyncSession, tenant_id: int, currency: str = "OMR"):
        self.db = db
        self.tenant_id = tenant_id
        self.currency = currency

    async def income_statement(
        self, start_date: date, end_date: date
    ) -> IncomeStatementResponse:
        return await generators.generate_income_statement(
            self.db, self.tenant_id, start_date, end_date, self.currency
        )

    async def balance_sheet(self, as_of_date: date) -> BalanceSheetResponse:
        return await generators.generate_balance_sheet(
            self.db, self.tenant_id, as_of_date, self.currency
        )

    async def cash_flow(self, start_date: date, end_date: date) -> CashFlowResponse:
        return await generators.generate_cash_flow(
            self.db, self.tenant_id, start_date, end_date, self.currency
        )

    async def net_worth(self, as_of_date: date) -> NetWorthResponse:
        return await generators.generate_net_worth(
            self.db, self.tenant_id, as_of_date, self.currency
        )

    async def expense_analysis(
        self, start_date: date, end_date: date
    ) -> ExpenseAnalysisResponse:
        return await generators.generate_expense_analysis(
            self.db, self.tenant_id, start_date, end_date, self.currency
        )
