from app.tasks.celery_app import celery_app
from app.models.database import async_session
from datetime import date, timedelta


@celery_app.task
async def detect_subscriptions():
    """Detect recurring subscriptions from transaction patterns."""
    async with async_session() as db:
        from app.models import JournalEntry, JournalLine, Account, Subscription
        from sqlalchemy import select, func
        
        # Find recurring transactions with same amount and similar dates
        thirty_days_ago = date.today() - timedelta(days=90)
        
        result = await db.execute(
            select(JournalLine.account_id, JournalLine.debit, func.count(JournalLine.id))
            .join(JournalEntry)
            .where(JournalEntry.date >= thirty_days_ago)
            .where(JournalLine.debit > 0)
            .group_by(JournalLine.account_id, JournalLine.debit)
            .having(func.count(JournalLine.id) >= 2)
        )
        patterns = result.all()
        
        # TODO: Create Subscription records for detected patterns
        for account_id, amount, count in patterns:
            pass
