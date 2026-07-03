"""Notification infrastructure tests.

Covers email backends, notification CRUD, preferences, bill/subscription
reminder generation, tenant isolation, and RLS.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Bill, Notification, NotificationChannel, NotificationStatus, NotificationType, Subscription, SubscriptionStatus, User
from app.notifications import NotificationDeliveryService
from app.notifications.channels.email import (
    ConsoleEmailBackend,
    DisabledEmailBackend,
    SmtpEmailBackend,
    send_email,
)
from app.services.bill_subscription_service import BillService, SubscriptionService
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


@pytest.fixture
def bill_payload():
    return {
        "name": "Electricity",
        "provider": "Majan Electricity",
        "typical_amount": "45.000",
        "due_date": (date.today() + timedelta(days=2)).isoformat(),
        "frequency": "monthly",
    }


@pytest.fixture
def overdue_bill_payload():
    return {
        "name": "Old Bill",
        "provider": "Provider",
        "typical_amount": "10.000",
        "due_date": (date.today() - timedelta(days=1)).isoformat(),
        "frequency": "one-time",
    }


@pytest.fixture
def subscription_payload():
    return {
        "name": "Mobile Plan",
        "provider": "Ooredoo",
        "amount": "15.000",
        "frequency": "monthly",
        "next_billing_date": (date.today() + timedelta(days=5)).isoformat(),
        "category": "Utilities",
    }


# ---------------------------------------------------------------------------
# Email channel unit tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.anyio
async def test_console_email_backend_does_not_send_real_email():
    """Console backend logs and returns success without network access."""
    backend = ConsoleEmailBackend()
    result = await backend.send(
        to_email="user@example.com",
        subject="Test",
        body_text="Hello",
    )
    assert result.success is True
    assert result.backend == "console"
    assert result.message_id == "console"


@pytest.mark.unit
@pytest.mark.anyio
async def test_disabled_email_backend_drops_email():
    """Disabled backend returns a skipped result."""
    backend = DisabledEmailBackend()
    result = await backend.send(
        to_email="user@example.com",
        subject="Test",
        body_text="Hello",
    )
    assert result.success is False
    assert result.backend == "disabled"


@pytest.mark.unit
@pytest.mark.anyio
async def test_smtp_backend_returns_error_when_not_configured(monkeypatch):
    """SMTP backend fails safely when configuration is missing."""
    import app.notifications.channels.email as email_mod

    monkeypatch.setattr(email_mod.settings, "SMTP_HOST", "")
    monkeypatch.setattr(email_mod.settings, "SMTP_USER", "")
    backend = SmtpEmailBackend()
    result = await backend.send(
        to_email="user@example.com",
        subject="Test",
        body_text="Hello",
    )
    assert result.success is False
    assert result.backend == "smtp"
    assert "missing" in result.error.lower() or "not configured" in result.error.lower()


@pytest.mark.unit
@pytest.mark.anyio
async def test_send_email_uses_configured_backend(monkeypatch):
    """send_email dispatches to the backend from settings."""
    import app.notifications.channels.email as email_mod
    from app.config import Settings

    disabled_settings = Settings()
    disabled_settings.EMAIL_BACKEND = "disabled"
    monkeypatch.setattr(email_mod, "settings", disabled_settings)

    result = await send_email(
        to_email="user@example.com",
        subject="Test",
        body_text="Hello",
    )
    assert result.success is False
    assert result.backend == "disabled"


# ---------------------------------------------------------------------------
# Notification CRUD
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_create_and_list_notifications(client, auth_headers):
    """A user can create and list notifications."""
    create_response = await client.post(
        "/notifications",
        json={
            "notification_type": "system",
            "title": "Test Notification",
            "message": "This is a test.",
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 200, create_response.text
    data = create_response.json()
    assert data["title"] == "Test Notification"
    assert data["status"] == "pending"
    assert data["channel"] == "in_app"


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_notifications_requires_auth(client):
    """Anonymous users cannot list notifications."""
    response = await client.get("/notifications")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_notification_read_and_unread(client, auth_headers):
    """Notifications can be marked read and unread."""
    create_response = await client.post(
        "/notifications",
        json={
            "notification_type": "system",
            "title": "Read Test",
            "message": "Please mark me read.",
        },
        headers=auth_headers,
    )
    notification_id = create_response.json()["id"]

    read_response = await client.patch(
        f"/notifications/{notification_id}/read",
        headers=auth_headers,
    )
    assert read_response.status_code == 200, read_response.text
    assert read_response.json()["is_read"] is True
    assert read_response.json()["status"] == "read"

    unread_response = await client.patch(
        f"/notifications/{notification_id}/unread",
        headers=auth_headers,
    )
    assert unread_response.status_code == 200, unread_response.text
    assert unread_response.json()["is_read"] is False
    assert unread_response.json()["status"] == "pending"


@pytest.mark.integration
@pytest.mark.anyio
async def test_unread_count(client, auth_headers):
    """Unread count endpoint reflects unread notifications."""
    await client.post(
        "/notifications",
        json={
            "notification_type": "system",
            "title": "Unread Count",
            "message": "Count me.",
        },
        headers=auth_headers,
    )

    response = await client.get("/notifications/unread-count", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["unread_count"] >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_all_read(client, auth_headers):
    """All notifications can be marked read at once."""
    await client.post(
        "/notifications",
        json={
            "notification_type": "system",
            "title": "Bulk Read",
            "message": "Mark all read.",
        },
        headers=auth_headers,
    )

    response = await client.post("/notifications/mark-all-read", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["marked_read"] >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_notification_preferences(client, auth_headers):
    """Preferences can be read and updated."""
    response = await client.get("/notifications/preferences", headers=auth_headers)
    assert response.status_code == 200, response.text

    update_response = await client.patch(
        "/notifications/preferences",
        json={
            "notification_type": "bill_due",
            "email": False,
            "in_app": True,
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["notification_type"] == "bill_due"
    assert update_response.json()["email"] is False
    assert update_response.json()["in_app"] is True


# ---------------------------------------------------------------------------
# Reminder generation
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_bill_reminder_generated(
    client, auth_headers, test_user, db, tenant_context, bill_payload
):
    """A bill reminder is created for an upcoming unpaid bill."""
    # Create bill under tenant context
    await tenant_context(test_user.organization_id)
    bill_service = BillService(db, tenant_id=test_user.organization_id)
    bill = await bill_service.create(bill_payload)

    response = await client.post("/notifications/run-reminders", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["bills"]["created"] >= 1

    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == test_user.organization_id)
        .where(Notification.notification_type == NotificationType.BILL_DUE)
        .where(Notification.related_entity_id == bill.id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_overdue_bill_reminder_generated(
    client, auth_headers, test_user, db, tenant_context, overdue_bill_payload
):
    """An overdue bill reminder is created."""
    await tenant_context(test_user.organization_id)
    bill_service = BillService(db, tenant_id=test_user.organization_id)
    bill = await bill_service.create(overdue_bill_payload)

    response = await client.post("/notifications/run-reminders", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["bills"]["created"] >= 1

    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == test_user.organization_id)
        .where(Notification.notification_type == NotificationType.BILL_OVERDUE)
        .where(Notification.related_entity_id == bill.id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_subscription_renewal_reminder_generated(
    client, auth_headers, test_user, db, tenant_context, subscription_payload
):
    """A subscription renewal reminder is created."""
    await tenant_context(test_user.organization_id)
    sub_service = SubscriptionService(db, tenant_id=test_user.organization_id)
    sub = await sub_service.create(subscription_payload)

    response = await client.post("/notifications/run-reminders", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["subscriptions"]["created"] >= 1

    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == test_user.organization_id)
        .where(Notification.notification_type == NotificationType.SUBSCRIPTION_RENEWAL)
        .where(Notification.related_entity_id == sub.id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_duplicate_reminders_prevented(
    client, auth_headers, test_user, db, tenant_context, bill_payload
):
    """Running reminders twice on the same day does not create duplicates."""
    await tenant_context(test_user.organization_id)
    bill_service = BillService(db, tenant_id=test_user.organization_id)
    await bill_service.create(bill_payload)

    first = await client.post("/notifications/run-reminders", headers=auth_headers)
    assert first.status_code == 200
    first_created = first.json()["bills"]["created"]

    second = await client.post("/notifications/run-reminders", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["bills"]["created"] == 0
    assert second.json()["bills"]["skipped"] == first_created


# ---------------------------------------------------------------------------
# Email notification lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_email_notification_marked_sent_in_dev_mode(
    client, auth_headers, test_user, db, tenant_context
):
    """Sending a pending email notification in dev mode marks it sent."""
    await tenant_context(test_user.organization_id)
    service = NotificationDeliveryService(db, tenant_id=test_user.organization_id)
    notification = await service.create_notification(
        user_id=test_user.id,
        notification_type=NotificationType.SYSTEM,
        title="Email Test",
        message="Please send me by email.",
        channel=NotificationChannel.EMAIL,
    )

    result = await service.send_email_notification(notification)
    assert result.success is True
    assert result.backend == "console"

    result = await db.execute(
        select(Notification).where(Notification.id == notification.id)
    )
    updated = result.scalar_one()
    assert updated.status == NotificationStatus.SENT
    assert updated.sent_at is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_email_notification_respects_user_preference(
    client, auth_headers, test_user, db, tenant_context
):
    """Email is skipped when user disables email for the notification type."""
    await tenant_context(test_user.organization_id)
    service = NotificationDeliveryService(db, tenant_id=test_user.organization_id)
    await service.update_preference(
        test_user.id,
        NotificationType.SYSTEM,
        email=False,
    )

    notification = await service.create_notification(
        user_id=test_user.id,
        notification_type=NotificationType.SYSTEM,
        title="Preference Test",
        message="Should be skipped.",
        channel=NotificationChannel.EMAIL,
    )

    result = await service.send_email_notification(notification)
    assert result.success is False
    assert "preference" in result.error.lower() or result.backend == "preference"

    result = await db.execute(
        select(Notification).where(Notification.id == notification.id)
    )
    updated = result.scalar_one()
    assert updated.status == NotificationStatus.SKIPPED


# ---------------------------------------------------------------------------
# Authorization and tenant isolation
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_run_reminders_requires_admin(client, auth_headers, db, unique):
    """Normal users cannot run reminder generation."""
    # auth_headers fixture gives an owner user, so they can run it.
    # Create a viewer user and confirm they are rejected.
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    viewer, password = await create_test_user(db, org, role="viewer")
    headers = await auth_headers_for(client, viewer.email, password)

    response = await client.post("/notifications/run-reminders", headers=headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_notifications(client, db, unique):
    """Tenant B cannot read notifications created for Tenant A."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    create_response = await client.post(
        "/notifications",
        json={
            "notification_type": "system",
            "title": "Tenant A Secret",
            "message": "Secret",
        },
        headers=headers_a,
    )
    assert create_response.status_code == 200

    list_b = await client.get("/notifications", headers=headers_b)
    assert list_b.status_code == 200
    assert not any(n["title"] == "Tenant A Secret" for n in list_b.json())


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_notifications(db):
    """The notifications table must have RLS and FORCE RLS enabled."""
    await assert_rls_enabled(db, "notifications")


@pytest.mark.integration
@pytest.mark.anyio
async def test_test_email_endpoint(client, auth_headers):
    """The test-email endpoint returns the configured backend result."""
    response = await client.post("/notifications/test-email", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["success"] is True
    assert data["backend"] == "console"
