from app.tasks.celery_app import celery_app
from app.models.database import async_session
from app.models import RecurringTransaction, JournalEntry, JournalLine
from app.services.accounting_service import AccountingService
from datetime import datetime, date


@celery_app.task
async def generate_recurring_transactions():
    """Generate journal entries from recurring transaction templates."""
    async with async_session() as db:
        # Get all active recurring transactions due today or earlier
        result = await db.execute(
            select(RecurringTransaction)
            .where(RecurringTransaction.is_active == True)
            .where(RecurringTransaction.next_date <= date.today())
        )
        recurring = result.scalars().all()
        
        for rec in recurring:
            # Create journal entry
            entry_data = JournalEntryCreate(
                date=rec.next_date,
                narration=rec.narration,
                lines=[
                    JournalLineCreate(
                        account_id=rec.debit_account_id,
                        debit=rec.amount,
                        credit=Decimal('0'),
                    ),
                    JournalLineCreate(
                        account_id=rec.credit_account_id,
                        debit=Decimal('0'),
                        credit=rec.amount,
                    ),
                ]
            )
            
            service = AccountingService(db, rec.tenant_id)
            await service.create_journal_entry(entry_data)
            
            # Update next date
            rec.last_generated_at = datetime.utcnow()
            if rec.frequency == "daily":
                rec.next_date = rec.next_date + timedelta(days=1)
            elif rec.frequency == "weekly":
                rec.next_date = rec.next_date + timedelta(weeks=1)
            elif rec.frequency == "monthly":
                rec.next_date = rec.next_date + timedelta(days=30)
            elif rec.frequency == "yearly":
                rec.next_date = rec.next_date + timedelta(days=365)
            
            # Check if end date reached
            if rec.end_date and rec.next_date > rec.end_date:
                rec.is_active = False
        
        await db.commit()
