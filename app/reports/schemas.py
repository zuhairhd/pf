from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class ReportAccountRow(BaseModel):
    """A single account row inside a report."""

    account_id: int
    account_code: str
    account_name: str
    amount: Decimal


class IncomeStatementResponse(BaseModel):
    """Profit & loss report for a date range."""

    start_date: date
    end_date: date
    currency: str
    income_total: Decimal
    expense_total: Decimal
    net_income: Decimal
    income_accounts: List[ReportAccountRow]
    expense_accounts: List[ReportAccountRow]


class BalanceSheetResponse(BaseModel):
    """Balance sheet as of a given date."""

    as_of_date: date
    currency: str
    assets_total: Decimal
    liabilities_total: Decimal
    equity_total: Decimal
    net_worth: Decimal
    balance_check: bool
    asset_accounts: List[ReportAccountRow]
    liability_accounts: List[ReportAccountRow]
    equity_accounts: List[ReportAccountRow]


class CashFlowAccountRow(BaseModel):
    """Cash flow detail for one cash account."""

    account_id: int
    account_code: str
    account_name: str
    inflow: Decimal
    outflow: Decimal
    net: Decimal


class CashFlowResponse(BaseModel):
    """Cash flow summary for a date range."""

    start_date: date
    end_date: date
    currency: str
    cash_inflow: Decimal
    cash_outflow: Decimal
    net_cash_flow: Decimal
    by_account: List[CashFlowAccountRow]


class NetWorthAccountRow(BaseModel):
    """Net worth detail for one asset or liability account."""

    account_id: int
    account_code: str
    account_name: str
    account_type: str
    amount: Decimal


class NetWorthResponse(BaseModel):
    """Net worth summary as of a given date."""

    as_of_date: date
    currency: str
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    accounts: List[NetWorthAccountRow]


class ExpenseAccountRow(BaseModel):
    """Expense analysis row for one expense account."""

    account_id: int
    account_code: str
    account_name: str
    amount: Decimal
    percent_of_total: Decimal


class ExpenseAnalysisResponse(BaseModel):
    """Expense analysis report for a date range."""

    start_date: date
    end_date: date
    currency: str
    total_expenses: Decimal
    expenses_by_account: List[ExpenseAccountRow]
    top_expense_accounts: List[ExpenseAccountRow]
