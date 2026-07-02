from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import get_db
from app.models import User, Organization, AITokenUsage, AuditLog
from app.config import get_settings
from app.services.admin_access_service import AdminAccessService
from app.schemas.admin import (
    AdminAccessStartRequest,
    AdminAccessSessionResponse,
)
from app.core.admin_context import AdminAccessError
from app.core.security import require_super_admin

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """Super admin dashboard."""
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
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """List all tenants."""
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    tenants = result.scalars().all()

    return tenants


@router.post("/support-access/start", response_model=AdminAccessSessionResponse)
async def start_support_access(
    request: Request,
    payload: AdminAccessStartRequest,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """Start an audited support session for exactly one tenant.

    Sets the database RLS context to the target organization so that all
    subsequent queries in the same transaction are filtered by normal tenant
    policies. There is no universal bypass.
    """
    service = AdminAccessService(db)

    try:
        session = await service.start_support_session(
            admin_user=admin_user,
            target_organization_id=payload.target_organization_id,
            reason=payload.reason,
            request=request,
            expires_minutes=payload.expires_minutes,
        )
        await db.commit()
    except AdminAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return session


@router.post("/support-access/{access_session_id}/end", response_model=AdminAccessSessionResponse)
async def end_support_access(
    access_session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """End an active support session and clear the RLS tenant context."""
    service = AdminAccessService(db)

    try:
        session = await service.end_support_session(
            access_session_id=access_session_id,
            admin_user_id=admin_user.id,
        )
        await db.commit()
    except AdminAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return session


@router.get("/support-access/active", response_model=AdminAccessSessionResponse)
async def get_active_support_access(
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """Return the current admin's active support session, if any."""
    service = AdminAccessService(db)

    session = await service.get_active_session(admin_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="No active support session")

    return session


@router.get("/support-access/recent", response_model=list[AdminAccessSessionResponse])
async def list_recent_support_access(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_super_admin),
):
    """List recent support access sessions for the current admin."""
    service = AdminAccessService(db)

    sessions = await service.list_recent_sessions(admin_user.id, limit=limit)
    return sessions
