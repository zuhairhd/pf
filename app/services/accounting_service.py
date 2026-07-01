from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from app.models import Account, JournalEntry, JournalLine, RecurringTransaction
from app.schemas.accounting import AccountCreate, JournalEntryCreate, TransferCreate


class AccountingService:
    """Double-entry accounting engine service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def create_account(self, account_data: AccountCreate) -> Account:
        """Create a new account in the chart of accounts."""
        account = Account(
            tenant_id=self.tenant_id,
            code=account_data.code,
            name=account_data.name,
            account_type=account_data.account_type,
            parent_account_id=account_data.parent_account_id,
            description=account_data.description,
            is_bank_account=account_data.is_bank_account,
            is_cash_account=account_data.is_cash_account,
            is_credit_card=account_data.is_credit_card,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account
    
    async def get_account_balance(self, account_id: int, from_date: Optional[date] = None, to_date: Optional[date] = None) -> Decimal:
        """Calculate the balance of an account."""
        result = await self.db.execute(
            select(Account).where(Account.id == account_id).where(Account.tenant_id == self.tenant_id)
        )
        account = result.scalar_one_or_none()
        if not account:
            return Decimal('0')
        
        query = select(
            func.coalesce(func.sum(JournalLine.debit), Decimal('0')),
            func.coalesce(func.sum(JournalLine.credit), Decimal('0'))
        ).join(JournalEntry).where(JournalLine.account_id == account_id)
        
        if from_date:
            query = query.where(JournalEntry.date >= from_date)
        if to_date:
            query = query.where(JournalEntry.date <= to_date)
        
        result = await self.db.execute(query)
        total_debit, total_credit = result.one()
        
        # Calculate net balance based on account type
        if account.account_type in ('Asset', 'Expense'):
            return total_debit - total_credit
        else:
            return total_credit - total_debit
    
    async def create_journal_entry(self, entry_data: JournalEntryCreate) -> JournalEntry:
        """Create a new journal entry with validation."""
        # Validate debits = credits
        total_debit = sum(line.debit for line in entry_data.lines)
        total_credit = sum(line.credit for line in entry_data.lines)
        
        if total_debit != total_credit:
            raise ValueError(f"Journal entry must balance. Debit: {total_debit}, Credit: {total_credit}")
        
        if len(entry_data.lines) < 2:
            raise ValueError("Journal entry must have at least two lines")
        
        # Generate reference
        ref = await self._generate_reference(entry_data.date)
        
        entry = JournalEntry(
            tenant_id=self.tenant_id,
            date=entry_data.date,
            reference=ref,
            narration=entry_data.narration,
            person_id=entry_data.person_id,
        )
        self.db.add(entry)
        await self.db.flush()
        
        # Add lines
        for line_data in entry_data.lines:
            line = JournalLine(
                tenant_id=self.tenant_id,
                journal_entry_id=entry.id,
                account_id=line_data.account_id,
                debit=line_data.debit,
                credit=line_data.credit,
                description=line_data.description,
            )
            self.db.add(line)
        
        await self.db.commit()
        await self.db.refresh(entry)
        return entry
    
    async def create_transfer(self, transfer_data: TransferCreate) -> JournalEntry:
        """Create a transfer between accounts (auto-balanced journal entry)."""
        narration = transfer_data.narration or f"Transfer: {transfer_data.amount}"
        
        entry_data = JournalEntryCreate(
            date=transfer_data.date,
            narration=narration,
            lines=[
                JournalLineCreate(
                    account_id=transfer_data.to_account_id,
                    debit=transfer_data.amount,
                    credit=Decimal('0'),
                    description=f"Transfer from account {transfer_data.from_account_id}",
                ),
                JournalLineCreate(
                    account_id=transfer_data.from_account_id,
                    debit=Decimal('0'),
                    credit=transfer_data.amount,
                    description=f"Transfer to account {transfer_data.to_account_id}",
                ),
            ]
        )
        
        return await self.create_journal_entry(entry_data)
    
    async def _generate_reference(self, entry_date: date) -> str:
        """Generate a unique reference number for a journal entry."""
        year = entry_date.year
        result = await self.db.execute(
            select(func.count(JournalEntry.id))
            .where(JournalEntry.tenant_id == self.tenant_id)
            .where(func.extract('year', JournalEntry.date) == year)
        )
        count = result.scalar() + 1
        return f"JE-{year}-{count:04d}"
    
    async def get_trial_balance(self, from_date: Optional[date] = None, to_date: Optional[date] = None) -> List[Dict]:
        """Generate trial balance report."""
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).order_by(Account.code)
        )
        accounts = result.scalars().all()
        
        rows = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for account in accounts:
            balance = await self.get_account_balance(account.id, from_date, to_date)
            if balance != 0:
                if balance > 0:
                    debit = balance
                    credit = Decimal('0')
                else:
                    debit = Decimal('0')
                    credit = abs(balance)
                
                rows.append({
                    'account': account,
                    'debit': debit,
                    'credit': credit,
                })
                total_debit += debit
                total_credit += credit
        
        return {
            'rows': rows,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'balanced': total_debit == total_credit,
        }
    
    async def get_income_statement(self, from_date: date, to_date: date) -> Dict:
        """Generate income statement (profit & loss)."""
        # Income
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Income')
        )
        income_accounts = result.scalars().all()
        
        income_rows = []
        total_income = Decimal('0')
        for account in income_accounts:
            balance = await self.get_account_balance(account.id, from_date, to_date)
            income_rows.append({'account': account, 'balance': balance})
            total_income += balance
        
        # Expenses
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Expense')
        )
        expense_accounts = result.scalars().all()
        
        expense_rows = []
        total_expenses = Decimal('0')
        for account in expense_accounts:
            balance = await self.get_account_balance(account.id, from_date, to_date)
            expense_rows.append({'account': account, 'balance': balance})
            total_expenses += balance
        
        surplus = total_income - total_expenses
        
        return {
            'income_rows': income_rows,
            'expense_rows': expense_rows,
            'total_income': total_income,
            'total_expenses': total_expenses,
            'surplus': surplus,
        }
    
    async def get_balance_sheet(self) -> Dict:
        """Generate balance sheet (net worth statement)."""
        # Assets
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Asset')
        )
        asset_accounts = result.scalars().all()
        
        asset_rows = []
        total_assets = Decimal('0')
        for account in asset_accounts:
            balance = await self.get_account_balance(account.id)
            asset_rows.append({'account': account, 'balance': balance})
            total_assets += balance
        
        # Liabilities
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Liability')
        )
        liability_accounts = result.scalars().all()
        
        liability_rows = []
        total_liabilities = Decimal('0')
        for account in liability_accounts:
            balance = await self.get_account_balance(account.id)
            liability_rows.append({'account': account, 'balance': balance})
            total_liabilities += balance
        
        # Equity
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Equity')
        )
        equity_accounts = result.scalars().all()
        
        equity_rows = []
        total_equity = Decimal('0')
        for account in equity_accounts:
            balance = await self.get_account_balance(account.id)
            equity_rows.append({'account': account, 'balance': balance})
            total_equity += balance
        
        net_worth = total_assets - total_liabilities
        
        return {
            'asset_rows': asset_rows,
            'liability_rows': liability_rows,
            'equity_rows': equity_rows,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            'net_worth': net_worth,
        }
