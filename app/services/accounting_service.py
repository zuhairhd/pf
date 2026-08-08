from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from app.models import Account, JournalEntry, JournalLine, RecurringTransaction
from app.schemas.accounting import AccountCreate, JournalEntryCreate, JournalLineCreate, TransferCreate


class AccountingService:
    """Double-entry accounting engine service."""

    # Well-known tenant-scoped equity account used as the offsetting side of
    # opening balance postings (ACC-502). Matches the naming already used by
    # the default seeded chart of accounts (app/seeds/default_data.py).
    OPENING_BALANCE_EQUITY_CODE = "3000"
    OPENING_BALANCE_EQUITY_NAME = "Opening Balance"

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
            visibility=account_data.visibility or "private",
            owner_user_id=account_data.owner_user_id,
            family_id=account_data.family_id,
            opening_balance=getattr(account_data, "opening_balance", None),
            opening_balance_date=getattr(account_data, "opening_balance_date", None),
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account
    
    # -------------------------------------------------------------------
    # Opening balances (ACC-502)
    # -------------------------------------------------------------------

    async def _opening_balance_candidate_accounts(
        self, account_ids: Optional[List[int]]
    ) -> List[Account]:
        query = select(Account).where(Account.tenant_id == self.tenant_id)
        if account_ids is not None:
            query = query.where(Account.id.in_(account_ids))
        result = await self.db.execute(query.order_by(Account.code))
        return list(result.scalars().all())

    async def _find_opening_balance_equity_account(self) -> Optional[Account]:
        """Look up the tenant's opening-balance offset account, if any exists."""
        result = await self.db.execute(
            select(Account).where(
                Account.tenant_id == self.tenant_id,
                Account.account_type == "Equity",
            ).where(
                (Account.code == self.OPENING_BALANCE_EQUITY_CODE)
                | (func.lower(Account.name) == self.OPENING_BALANCE_EQUITY_NAME.lower())
            )
        )
        return result.scalars().first()

    async def _get_or_create_opening_balance_equity_account(self) -> Account:
        """Return the tenant's opening-balance offset account, creating it if absent.

        Reuses create_account() unchanged and the exact naming already used
        by the default seeded chart of accounts, so a tenant that already
        seeded one (code 3000, "Opening Balance") gets it reused rather than
        duplicated.
        """
        existing = await self._find_opening_balance_equity_account()
        if existing is not None:
            return existing
        return await self.create_account(
            AccountCreate(
                code=self.OPENING_BALANCE_EQUITY_CODE,
                name=self.OPENING_BALANCE_EQUITY_NAME,
                account_type="Equity",
                description="System-managed equity offset account for opening balance postings.",
            )
        )

    def _classify_opening_balance_account(
        self, account: Account, equity_account_id: Optional[int]
    ) -> Tuple[str, Optional[Decimal]]:
        """Return (status, amount) for an account without touching the database."""
        if equity_account_id is not None and account.id == equity_account_id:
            return "skipped_offset_account", account.opening_balance
        if account.opening_balance_journal_entry_id is not None:
            return "already_posted", account.opening_balance
        if account.opening_balance is None:
            return "skipped_no_balance", None
        if account.opening_balance == 0:
            return "skipped_zero", Decimal("0")
        return "pending", account.opening_balance

    @staticmethod
    def _opening_balance_line_amounts(
        account: Account, amount: Decimal
    ) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """Return (account_debit, account_credit, equity_debit, equity_credit).

        Respects each account type's normal balance side (Asset/Expense are
        normally debit-balance; Liability/Equity/Income are normally
        credit-balance) and flips sides safely for a negative opening amount,
        always keeping the pair balanced.
        """
        abs_amount = abs(amount)
        normal_debit = account.account_type in ("Asset", "Expense")
        if (amount >= 0) == normal_debit:
            account_debit, account_credit = abs_amount, Decimal("0")
        else:
            account_debit, account_credit = Decimal("0"), abs_amount
        # The equity offset always takes the opposite side of the account line.
        equity_debit, equity_credit = account_credit, account_debit
        return account_debit, account_credit, equity_debit, equity_credit

    @staticmethod
    def _opening_balance_row(
        account: Account, status: str, amount: Optional[Decimal], journal_entry_id: Optional[int]
    ) -> dict:
        return {
            "account_id": account.id,
            "code": account.code,
            "name": account.name,
            "account_type": account.account_type,
            "status": status,
            "amount": amount,
            "journal_entry_id": journal_entry_id,
        }

    async def get_opening_balance_status(
        self, account_ids: Optional[List[int]] = None
    ) -> Dict:
        """Read-only preview of what post_opening_balances() would do.

        Never creates or modifies any record.
        """
        accounts = await self._opening_balance_candidate_accounts(account_ids)
        equity_account = await self._find_opening_balance_equity_account()
        equity_account_id = equity_account.id if equity_account else None

        results = []
        pending = already_posted = skipped = 0
        for account in accounts:
            status, amount = self._classify_opening_balance_account(account, equity_account_id)
            results.append(
                self._opening_balance_row(
                    account, status, amount, account.opening_balance_journal_entry_id
                )
            )
            if status == "pending":
                pending += 1
            elif status == "already_posted":
                already_posted += 1
            else:
                skipped += 1

        return {
            "accounts_considered": len(accounts),
            "accounts_pending": pending,
            "accounts_already_posted": already_posted,
            "accounts_skipped": skipped,
            "opening_balance_equity_account_id": equity_account_id,
            "results": results,
        }

    async def post_opening_balances(
        self,
        account_ids: Optional[List[int]] = None,
        posted_by: Optional[int] = None,
    ) -> Dict:
        """Post configured opening balances into real, idempotent journal entries.

        For each tenant account with a non-null, non-zero opening_balance
        that has not already been posted, creates a single balanced journal
        entry against a tenant-scoped "Opening Balance" Equity account
        (auto-created if absent, reusing create_account() unchanged) via the
        existing create_journal_entry() -- never a direct insert. Idempotent:
        an account whose opening_balance_journal_entry_id is already set is
        left untouched and reported as already_posted, never re-posted or
        duplicated. Null/zero opening balances are skipped safely and never
        produce a journal line.
        """
        accounts = await self._opening_balance_candidate_accounts(account_ids)
        equity_account = await self._find_opening_balance_equity_account()
        equity_account_id = equity_account.id if equity_account else None

        results = []
        pending: List[Tuple[Account, Decimal]] = []
        already_posted = skipped = 0

        for account in accounts:
            status, amount = self._classify_opening_balance_account(account, equity_account_id)
            if status == "pending":
                pending.append((account, amount))
                continue
            results.append(
                self._opening_balance_row(
                    account, status, amount, account.opening_balance_journal_entry_id
                )
            )
            if status == "already_posted":
                already_posted += 1
            else:
                skipped += 1

        total_debit = Decimal("0")
        total_credit = Decimal("0")
        posted = 0

        if pending:
            if equity_account is None:
                equity_account = await self._get_or_create_opening_balance_equity_account()
                equity_account_id = equity_account.id

            for account, amount in pending:
                account_debit, account_credit, equity_debit, equity_credit = (
                    self._opening_balance_line_amounts(account, amount)
                )
                entry = await self.create_journal_entry(
                    JournalEntryCreate(
                        date=account.opening_balance_date or date.today(),
                        narration=f"Opening balance: {account.name}",
                        reference=f"OB-{self.tenant_id}-{account.id}",
                        person_id=posted_by,
                        lines=[
                            JournalLineCreate(
                                account_id=account.id,
                                debit=account_debit,
                                credit=account_credit,
                                description="Opening balance",
                            ),
                            JournalLineCreate(
                                account_id=equity_account.id,
                                debit=equity_debit,
                                credit=equity_credit,
                                description=f"Opening balance offset: {account.name}",
                            ),
                        ],
                    )
                )
                account.opening_balance_journal_entry_id = entry.id
                await self.db.commit()
                await self.db.refresh(account)

                total_debit += account_debit + equity_debit
                total_credit += account_credit + equity_credit
                posted += 1
                results.append(self._opening_balance_row(account, "posted", amount, entry.id))

        return {
            "accounts_considered": len(accounts),
            "accounts_posted": posted,
            "accounts_already_posted": already_posted,
            "accounts_skipped": skipped,
            "opening_balance_equity_account_id": equity_account_id,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "results": results,
        }

    async def get_account_balance(
        self,
        account_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        exclude_reversed: bool = False,
    ) -> Decimal:
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
        if exclude_reversed:
            # Exclude original entries that have been reversed. Reversal entries
            # themselves (reversed_entry_id is set) are kept because they offset
            # the originals.
            query = query.where(JournalEntry.reversal_entry_id.is_(None))

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
        
        # Generate reference unless the caller supplies a deterministic one.
        ref = entry_data.reference or await self._generate_reference(entry_data.date)
        
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

    async def reverse_journal_entry(
        self,
        original_journal_entry_id: int,
        reversal_date: Optional[date] = None,
        reason: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> JournalEntry:
        """Create or return an idempotent reversing journal entry.

        The original posted entry and lines are never changed except for
        reversal metadata that points to the generated reversal entry.
        """
        result = await self.db.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(
                JournalEntry.id == original_journal_entry_id,
                JournalEntry.tenant_id == self.tenant_id,
            )
        )
        original = result.scalar_one_or_none()
        if original is None:
            raise ValueError("Journal entry not found")
        if original.reversed_entry_id is not None:
            raise ValueError("Cannot reverse a reversal journal entry")

        existing = await self._get_existing_reversal(original)
        if existing is not None:
            return existing

        if not original.lines:
            raise ValueError("Journal entry has no lines to reverse")

        effective_date = reversal_date or date.today()
        reason_text = reason or "No reason provided"
        reversal_reference = self._reversal_reference(original.id)

        reversal_lines = [
            JournalLineCreate(
                account_id=line.account_id,
                debit=line.credit,
                credit=line.debit,
                description=line.description or f"Reversal of {original.reference}",
            )
            for line in original.lines
        ]

        reversal = await self.create_journal_entry(
            JournalEntryCreate(
                date=effective_date,
                narration=f"Reversal of {original.reference}: {reason_text}",
                reference=reversal_reference,
                person_id=created_by,
                lines=reversal_lines,
            )
        )

        result = await self.db.execute(
            select(JournalEntry)
            .where(
                JournalEntry.id == original.id,
                JournalEntry.tenant_id == self.tenant_id,
            )
        )
        original = result.scalar_one()
        reversal.source = "reversal"
        reversal.reversed_entry_id = original.id
        reversal.reversal_reason = reason
        original.reversal_entry_id = reversal.id
        original.reversed_at = datetime.utcnow()
        original.reversal_reason = reason
        await self.db.commit()
        result = await self.db.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(
                JournalEntry.id == reversal.id,
                JournalEntry.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one()

    def _reversal_reference(self, original_journal_entry_id: int) -> str:
        """Return the deterministic tenant-aware reversal reference."""
        return f"REV-{self.tenant_id}-{original_journal_entry_id}"

    async def _get_existing_reversal(self, original: JournalEntry) -> Optional[JournalEntry]:
        """Return the already-created reversal for an original entry, if any."""
        if original.reversal_entry_id:
            result = await self.db.execute(
                select(JournalEntry)
                .options(selectinload(JournalEntry.lines))
                .where(
                    JournalEntry.id == original.reversal_entry_id,
                    JournalEntry.tenant_id == self.tenant_id,
                )
            )
            reversal = result.scalar_one_or_none()
            if reversal is not None:
                return reversal

        result = await self.db.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(
                JournalEntry.tenant_id == self.tenant_id,
                JournalEntry.reversed_entry_id == original.id,
            )
        )
        reversal = result.scalar_one_or_none()
        if reversal is None:
            result = await self.db.execute(
                select(JournalEntry)
                .options(selectinload(JournalEntry.lines))
                .where(
                    JournalEntry.tenant_id == self.tenant_id,
                    JournalEntry.reference == self._reversal_reference(original.id),
                )
            )
            reversal = result.scalar_one_or_none()

        if reversal is not None:
            original.reversal_entry_id = reversal.id
            if original.reversed_at is None:
                original.reversed_at = datetime.utcnow()
            await self.db.commit()
            return reversal
        return None
    
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
        """Generate a unique reference number for a journal entry.

        The reference includes the tenant id so that the globally-unique
        ``reference`` constraint cannot collide across tenants.
        """
        year = entry_date.year
        result = await self.db.execute(
            select(func.count(JournalEntry.id))
            .where(JournalEntry.tenant_id == self.tenant_id)
            .where(func.extract('year', JournalEntry.date) == year)
        )
        count = result.scalar() + 1
        return f"JE-{self.tenant_id}-{year}-{count:04d}"
    
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
    
    async def get_income_statement(
        self,
        from_date: date,
        to_date: date,
        exclude_reversed: bool = False,
    ) -> Dict:
        """Generate income statement (profit & loss)."""
        # Income
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Income')
        )
        income_accounts = result.scalars().all()

        income_rows = []
        total_income = Decimal('0')
        for account in income_accounts:
            balance = await self.get_account_balance(account.id, from_date, to_date, exclude_reversed)
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
            balance = await self.get_account_balance(account.id, from_date, to_date, exclude_reversed)
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
    
    async def get_balance_sheet(
        self,
        as_of_date: Optional[date] = None,
        exclude_reversed: bool = False,
    ) -> Dict:
        """Generate balance sheet (net worth statement)."""
        # Assets
        result = await self.db.execute(
            select(Account).where(Account.tenant_id == self.tenant_id).where(Account.account_type == 'Asset')
        )
        asset_accounts = result.scalars().all()

        asset_rows = []
        total_assets = Decimal('0')
        for account in asset_accounts:
            balance = await self.get_account_balance(account.id, None, as_of_date, exclude_reversed)
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
            balance = await self.get_account_balance(account.id, None, as_of_date, exclude_reversed)
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
            balance = await self.get_account_balance(account.id, None, as_of_date, exclude_reversed)
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
