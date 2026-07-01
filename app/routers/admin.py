from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import get_db
from app.models import User, Organization, AITokenUsage, AuditLog
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Super admin dashboard."""
    user_id = getattr(request.state, "user_id", None)
    
    # Check if superuser
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get stats
    total_users = await db.execute(select(func.count(User.id)))
    total_tenants = await db.execute(select(func.count(Organization.id)))
    total_ai_cost = await db.execute(select(func.sum(AITokenUsage.cost_usd)))
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "total_users": total_users.scalar(),
        "total_tenants": total_tenants.scalar(),
        "total_ai_cost": total_ai_cost.scalar() or 0,
    })


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """List all tenants."""
    user_id = getattr(request.state, "user_id", None)
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    tenants = result.scalars().all()
    
    return tenants
