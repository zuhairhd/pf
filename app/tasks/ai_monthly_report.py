from app.tasks.celery_app import celery_app
from app.models.database import async_session
from datetime import date


@celery_app.task
async def generate_monthly_reports():
    """Generate monthly AI reports for all active tenants."""
    async with async_session() as db:
        from app.models import Organization
        from app.models.ai import AIReport
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.is_active == True)
        )
        tenants = result.scalars().all()
        
        for tenant in tenants:
            try:
                report = AIReport(
                    tenant_id=tenant.id,
                    report_type="monthly",
                    period_start=date.today().replace(day=1),
                    period_end=date.today(),
                    title=f"Monthly Report - {date.today().strftime('%B %Y')}",
                    content="Monthly financial summary generated.",
                )
                db.add(report)
                await db.commit()
                
            except Exception as e:
                print(f"Error generating monthly report for tenant {tenant.id}: {e}")
