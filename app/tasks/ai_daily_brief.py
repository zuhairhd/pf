from app.tasks.celery_app import celery_app
from app.models.database import async_session
from app.services.ai_orchestrator import AIOrchestrator


@celery_app.task
async def generate_daily_briefs():
    """Generate daily AI briefs for all active tenants."""
    async with async_session() as db:
        # Get all active tenants
        from app.models import Organization
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.is_active == True)
        )
        tenants = result.scalars().all()
        
        for tenant in tenants:
            try:
                orchestrator = AIOrchestrator(db, tenant.id)
                await orchestrator.generate_daily_brief()
            except Exception as e:
                # Log error but continue with other tenants
                print(f"Error generating daily brief for tenant {tenant.id}: {e}")
