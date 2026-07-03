from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.security import get_db_with_tenant_context, require_active_user, require_tenant_member, require_tenant_admin
from app.models.database import get_db
from app.models import Notification, NotificationSetting, User
from app.schemas.notification import (
    NotificationCreate,
    NotificationPreferenceUpdate,
    NotificationResponse,
    NotificationPreferenceResponse,
    ReminderRunResponse,
    TestEmailResponse,
)
from app.services.notification_service import NotificationService
from app.notifications import NotificationDeliveryService
from app.notifications.channels.email import send_email
from app.config import get_settings

settings = get_settings()
router = APIRouter(tags=["Notifications"])
templates = Jinja2Templates(directory="app/templates")


def _to_response(notification: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        tenant_id=notification.tenant_id,
        user_id=notification.user_id,
        notification_type=notification.notification_type.value,
        title=notification.title,
        message=notification.message,
        channel=notification.channel.value,
        status=notification.status.value,
        is_read=notification.is_read,
        read_at=notification.read_at,
        scheduled_for=notification.scheduled_for,
        sent_at=notification.sent_at,
        error_message=notification.error_message,
        related_entity_type=notification.related_entity_type,
        related_entity_id=notification.related_entity_id,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


# ---------------------------------------------------------------------------
# HTML pages (legacy)
# ---------------------------------------------------------------------------

@router.get("/list", response_class=HTMLResponse)
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


@router.post("/{notification_id}/read-legacy")
async def mark_as_read_legacy(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read (legacy HTML endpoint)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    service = NotificationService(db, tenant_id)
    await service.mark_as_read(notification_id)

    return {"message": "Notification marked as read"}


@router.get("/settings-page", response_class=HTMLResponse)
async def notification_settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Notification settings page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)

    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})

    result = await db.execute(
        select(NotificationSetting).where(NotificationSetting.user_id == user_id)
    )
    settings_list = result.scalars().all()

    return templates.TemplateResponse("notifications/settings.html", {
        "request": request,
        "settings": settings_list,
    })


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List notifications for the current user."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    notifications = await service.list_notifications(
        user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return [_to_response(n) for n in notifications]


@router.post("", response_model=NotificationResponse)
async def create_notification(
    payload: NotificationCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a notification for the current user."""
    from app.models.notification import NotificationType

    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    try:
        notification_type = NotificationType(payload.notification_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid notification type") from exc

    notification = await service.create_notification(
        user_id=user.id,
        notification_type=notification_type,
        title=payload.title,
        message=payload.message,
    )
    return _to_response(notification)


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the count of unread notifications."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    count = await service.unread_count(user.id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a notification as read."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    notification = await service.mark_read(notification_id, user.id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_response(notification)


@router.patch("/{notification_id}/unread", response_model=NotificationResponse)
async def mark_notification_unread(
    notification_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a notification as unread."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    notification = await service.mark_unread(notification_id, user.id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_response(notification)


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark all notifications for the current user as read."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    count = await service.mark_all_read(user.id)
    return {"marked_read": count}


@router.get("/preferences", response_model=list[NotificationPreferenceResponse])
async def get_preferences(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get notification preferences for the current user."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    preferences = await service.get_preferences(user.id)
    return [
        NotificationPreferenceResponse.model_validate(p) for p in preferences
    ]


@router.patch("/preferences", response_model=NotificationPreferenceResponse)
async def update_preference(
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a notification preference."""
    from app.models.notification import NotificationType

    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    try:
        notification_type = NotificationType(payload.notification_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid notification type") from exc

    updated = await service.update_preference(
        user.id,
        notification_type,
        in_app=payload.in_app,
        email=payload.email,
        push=payload.push,
        sms=payload.sms,
        quiet_hours_start=payload.quiet_hours_start,
        quiet_hours_end=payload.quiet_hours_end,
    )
    return NotificationPreferenceResponse.model_validate(updated)


@router.post("/test-email", response_model=TestEmailResponse)
async def send_test_email(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Send a test email to the current user using the configured backend."""
    result = await send_email(
        to_email=user.email,
        subject="PF AI Personal Finance - Test Email",
        body_text=(
            "This is a test email from PF AI Personal Finance.\n"
            "If you received this, your email notification channel is configured correctly."
        ),
    )
    return TestEmailResponse(
        success=result.success,
        backend=result.backend,
        message_id=result.message_id,
        error=result.error,
    )


@router.post("/run-reminders", response_model=ReminderRunResponse)
async def run_reminders(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_admin),
):
    """Generate bill and subscription reminders for the current tenant.

    Requires tenant admin or higher. Safe to call repeatedly: duplicate
    reminders for the same entity on the same day are skipped.
    """
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    result = await service.generate_reminders(user)
    return ReminderRunResponse(**result)


@router.post("/send-pending-emails")
async def send_pending_emails(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_admin),
):
    """Send pending email notifications for the current tenant."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    result = await service.send_pending_email_notifications(limit=limit)
    return result
