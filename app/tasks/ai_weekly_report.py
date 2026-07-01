from app.tasks.celery_app import celery_app
from app.models.database import async_session
from app.services.ai_orchestrator import AIOrchestrator
from datetime import date


@celery_app.task
async def generate_weekly_reports():
    """Generate weekly AI reports for all active tenants."""
    async with async_session() as db:
        from app.models import Organization
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.is_active == True)
        )
        tenants = result.scalars().all()
        
        for tenant in tenants:
            try:
                orchestrator = AIOrchestrator(db, tenant.id)
                
                # Generate insights
                await orchestrator.generate_insights()
                
                # Create weekly report
                from app.models.ai import AIReport
                report = AIReport(
                    tenant_id=tenant.id,
                    report_type="weekly",
                    period_start=date.today() - __import__('datetime').timedelta(days=7),
                    period_end=date.today(),
                    title=f"Weekly Report - Week of {date.today().strftime('%B %d, %Y')}",
                    content="Weekly financial summary generated.",
                )
                db.add(report)
                await db.commit()
                
            except Exception as e:
                print(f"Error generating weekly report for tenant {tenant.id}: {e}")
