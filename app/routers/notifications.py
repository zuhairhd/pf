from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import Notification, NotificationSetting
from app.schemas.notification import NotificationCreate, NotificationSettingUpdate
from app.services.notification_service import NotificationService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def notifications_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Notifications list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == tenant_id)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    notifications = result.scalars().all()
    
    # Count unread
    unread_count = sum(1 for n in notifications if not n.is_read)
    
    return templates.TemplateResponse("notifications/list.html", {
        "request": request,
        "notifications": notifications,
        "unread_count": unread_count,
    })


@router.post("/{notification_id}/read")
async def mark_as_read(notification_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a notification as read."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = NotificationService(db, tenant_id)
    await service.mark_as_read(notification_id)
    
    return {"message": "Notification marked as read"}


@router.get("/settings", response_class=HTMLResponse)
async def notification_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Notification settings page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(NotificationSetting).where(NotificationSetting.user_id == user_id)
    )
    settings = result.scalars().all()
    
    return templates.TemplateResponse("notifications/settings.html", {
        "request": request,
        "settings": settings,
    })
