"""Import service for creating import jobs, validating rows, and posting
journal entries.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.imports.models import ImportJob, ImportedRow
from app.imports.parsers.csv_parser import CSVParser, compute_file_hash
from app.imports.schemas import ColumnMapping, ImportConfirmRequest
from app.models import Account, JournalEntry, JournalLine, User
from app.schemas.accounting import JournalEntryCreate, JournalLineCreate
from app.services.accounting_service import AccountingService


class ImportServiceError(Exception):
    """Raised when an import operation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ImportService:
    """Service for managing CSV imports and converting rows to journal entries."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def create_job(
        self,
        *,
        user: User,
        original_filename: str,
        file_content: str,
        mapping_hint: Optional[ColumnMapping] = None,
    ) -> ImportJob:
        """Parse a CSV file and create an import job with imported rows."""
        parser = CSVParser(file_content, mapping_hint)
        result = parser.parse()

        file_hash = compute_file_hash(file_content)

        job = ImportJob(
            tenant_id=self.tenant_id,
            user_id=user.id,
            import_type="csv",
            status="preview",
            original_filename=original_filename,
            file_hash=file_hash,
            mapping=result["mapping"],
            total_rows=result["total_rows"],
            valid_rows=result["valid_rows"],
            invalid_rows=result["invalid_rows"],
            duplicate_rows=0,
            imported_rows=0,
            errors=[],
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        # Build imported row records and detect duplicates within the file.
        duplicate_keys: dict[str, int] = {}
        imported_rows: list[ImportedRow] = []

        for parsed_row in result["rows"]:
            status = parsed_row.status
            duplicate_of: Optional[int] = None

            if status == "valid":
                dup_key = parsed_row.duplicate_key
                if dup_key in duplicate_keys:
                    status = "duplicate"
                    duplicate_of = duplicate_keys[dup_key]
                else:
                    duplicate_keys[dup_key] = 0  # placeholder, updated after insert

            row_record = ImportedRow(
                tenant_id=self.tenant_id,
                import_job_id=job.id,
                row_number=parsed_row.row_number,
                raw_data=parsed_row.raw_data,
                parsed_data=parsed_row.parsed_data,
                validation_errors=parsed_row.validation_errors,
                duplicate_key=parsed_row.duplicate_key if parsed_row.duplicate_key else None,
                duplicate_of_row_id=None,
                status=status,
            )
            self.db.add(row_record)
            imported_rows.append(row_record)

        await self.db.flush()

        # Update duplicate_of references now that IDs are known.
        key_to_id: dict[str, int] = {}
        for row_record in imported_rows:
            if row_record.status == "valid" and row_record.duplicate_key:
                key_to_id[row_record.duplicate_key] = row_record.id

        duplicate_count = 0
        for row_record in imported_rows:
            if row_record.status == "duplicate" and row_record.duplicate_key:
                row_record.duplicate_of_row_id = key_to_id.get(row_record.duplicate_key)
                duplicate_count += 1

        job.duplicate_rows = duplicate_count
        job.valid_rows = sum(1 for r in imported_rows if r.status == "valid")

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_job(self, job_id: int) -> Optional[ImportJob]:
        """Fetch a job by ID, scoped to the current tenant."""
        result = await self.db.execute(
            select(ImportJob).where(
                ImportJob.id == job_id,
                ImportJob.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_job_rows(
        self,
        job_id: int,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ImportedRow]:
        """Fetch rows for a job, optionally filtered by status."""
        query = (
            select(ImportedRow)
            .where(ImportedRow.import_job_id == job_id)
            .where(ImportedRow.tenant_id == self.tenant_id)
            .order_by(ImportedRow.row_number)
            .limit(limit)
            .offset(offset)
        )
        if status:
            query = query.where(ImportedRow.status == status)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def confirm_job(self, job_id: int, payload: ImportConfirmRequest) -> ImportJob:
        """Import valid, non-duplicate rows as journal entries."""
        job = await self.get_job(job_id)
        if job is None:
            raise ImportServiceError("Import job not found")
        if job.status in ("completed", "cancelled"):
            raise ImportServiceError(f"Import job is already {job.status}")

        rows = await self.get_job_rows(job_id, status="valid")
        if not rows:
            raise ImportServiceError("No valid rows available to import")

        accounting = AccountingService(self.db, self.tenant_id)

        imported_count = 0
        skipped_count = 0

        for row in rows:
            try:
                entry = await self._create_journal_entry_for_row(
                    row, accounting, payload
                )
                row.status = "imported"
                row.parsed_data["journal_entry_id"] = entry.id
                imported_count += 1
            except ImportServiceError as exc:
                row.status = "invalid"
                row.validation_errors.append(str(exc))
                skipped_count += 1

        job.imported_rows = imported_count
        job.status = "completed"
        job.completed_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def cancel_job(self, job_id: int) -> ImportJob:
        """Mark an import job as cancelled."""
        job = await self.get_job(job_id)
        if job is None:
            raise ImportServiceError("Import job not found")
        if job.status == "completed":
            raise ImportServiceError("Cannot cancel a completed import job")

        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def _create_journal_entry_for_row(
        self,
        row: ImportedRow,
        accounting: AccountingService,
        payload: ImportConfirmRequest,
    ) -> JournalEntry:
        """Convert a valid imported row into a journal entry."""
        parsed = row.parsed_data
        amount = Decimal(parsed.get("amount_decimal", "0"))
        txn_type = parsed.get("transaction_type", "expense")
        entry_date = datetime.fromisoformat(parsed["date"]).date()
        narration = parsed.get("description", "Imported transaction")
        reference = parsed.get("reference")

        bank_account = await self._get_account(payload.bank_account_id)
        if bank_account is None:
            raise ImportServiceError("Bank account not found")

        if txn_type == "expense":
            category_account = await self._resolve_category_account(
                parsed,
                default_account_id=payload.default_expense_account_id,
            )
            if category_account is None:
                raise ImportServiceError(
                    "Could not resolve expense category account for this row"
                )
            lines = [
                JournalLineCreate(
                    account_id=category_account.id,
                    debit=abs(amount),
                    credit=Decimal("0"),
                    description=narration,
                ),
                JournalLineCreate(
                    account_id=bank_account.id,
                    debit=Decimal("0"),
                    credit=abs(amount),
                    description=narration,
                ),
            ]
        elif txn_type == "income":
            category_account = await self._resolve_category_account(
                parsed,
                default_account_id=payload.default_income_account_id,
            )
            if category_account is None:
                raise ImportServiceError(
                    "Could not resolve income category account for this row"
                )
            lines = [
                JournalLineCreate(
                    account_id=bank_account.id,
                    debit=amount,
                    credit=Decimal("0"),
                    description=narration,
                ),
                JournalLineCreate(
                    account_id=category_account.id,
                    debit=Decimal("0"),
                    credit=amount,
                    description=narration,
                ),
            ]
        else:
            raise ImportServiceError(f"Unsupported transaction type: {txn_type}")

        entry_data = JournalEntryCreate(
            date=entry_date,
            narration=narration,
            lines=lines,
        )

        entry = await accounting.create_journal_entry(entry_data)
        # Override default source to mark as import.
        entry.source = "import"
        if reference:
            # Keep reference in narration if the unique constraint would clash.
            pass

        return entry

    async def _resolve_category_account(
        self, parsed: dict[str, Any], *, default_account_id: Optional[int]
    ) -> Optional[Account]:
        """Find the income/expense category account for a row."""
        category_value = parsed.get("category") or parsed.get("account")
        if category_value:
            account = await self._find_account(category_value)
            if account:
                return account

        if default_account_id:
            return await self._get_account(default_account_id)

        return None

    async def _find_account(self, identifier: str) -> Optional[Account]:
        """Look up an account by code or name within the tenant."""
        identifier = identifier.strip()
        # Try exact code match first.
        result = await self.db.execute(
            select(Account).where(
                Account.tenant_id == self.tenant_id,
                Account.code == identifier,
            )
        )
        account = result.scalar_one_or_none()
        if account:
            return account

        # Try name match (case-insensitive).
        result = await self.db.execute(
            select(Account).where(
                Account.tenant_id == self.tenant_id,
                Account.name.ilike(identifier),
            )
        )
        return result.scalar_one_or_none()

    async def _get_account(self, account_id: int) -> Optional[Account]:
        """Fetch an account by ID within the tenant."""
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()
