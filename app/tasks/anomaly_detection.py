from app.tasks.celery_app import celery_app
from app.models.database import async_session
from datetime import date, timedelta
from decimal import Decimal


@celery_app.task
async def detect_anomalies():
    """Detect spending and income anomalies."""
    async with async_session() as db:
        from app.models import JournalEntry, JournalLine, Account
        from app.models.ai import AIInsight, AIInsightType, AIInsightPriority
        from sqlalchemy import select, func
        
        # Get average monthly spending by category
        three_months_ago = date.today() - timedelta(days=90)
        
        result = await db.execute(
            select(
                Account.id,
                Account.name,
                func.avg(JournalLine.debit),
                func.stddev(JournalLine.debit)
            )
            .join(JournalLine, Account.id == JournalLine.account_id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.account_type == "Expense")
            .where(JournalEntry.date >= three_months_ago)
            .group_by(Account.id, Account.name)
        )
        averages = result.all()
        
        # Check current month for anomalies (> 2 standard deviations)
        current_month_start = date.today().replace(day=1)
        
        for account_id, account_name, avg, stddev in averages:
            if stddev is None or stddev == 0:
                continue
            
            result = await db.execute(
                select(func.sum(JournalLine.debit))
                .join(JournalEntry)
                .where(JournalLine.account_id == account_id)
                .where(JournalEntry.date >= current_month_start)
            )
            current_month = result.scalar() or Decimal('0')
            
            if float(current_month) > float(avg) + 2 * float(stddev):
                # Create anomaly insight
                insight = AIInsight(
                    tenant_id=account_id,  # This should be the actual tenant_id
                    insight_type=AIInsightType.EXPENSE,
                    priority=AIInsightPriority.MEDIUM,
                    title=f"Unusual Spending: {account_name}",
                    message=f"Your spending on {account_name} is significantly higher than usual this month.",
                    confidence=85,
                )
                db.add(insight)
        
        await db.commit()
