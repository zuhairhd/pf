from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import Goal, GoalContribution
from app.schemas.goal import GoalCreate, GoalUpdate, GoalContributionCreate
from app.services.goal_service import GoalService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def goals_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Goals list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Goal).where(Goal.tenant_id == tenant_id).where(Goal.status == "active")
    )
    goals = result.scalars().all()
    
    return templates.TemplateResponse("goals/list.html", {
        "request": request,
        "goals": goals,
    })


@router.post("/")
async def create_goal(goal: GoalCreate, db: AsyncSession = Depends(get_db)):
    """Create a new goal."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = GoalService(db, tenant_id)
    new_goal = await service.create_goal(goal)
    return new_goal


@router.post("/{goal_id}/contribute")
async def contribute_to_goal(goal_id: int, contribution: GoalContributionCreate, db: AsyncSession = Depends(get_db)):
    """Add a contribution to a goal."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = GoalService(db, tenant_id)
    new_contribution = await service.add_contribution(goal_id, contribution)
    return new_contribution
