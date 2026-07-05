"""API routes for subscriptions."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User
from app.schemas.bill_subscription import SubscriptionCreate, SubscriptionUpdate, SubscriptionResponse, MarkPaidRequest
from app.services.bill_subscription_service import SubscriptionService


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _to_response(subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=subscription.id,
        tenant_id=subscription.tenant_id,
        name=subscription.name,
        provider=subscription.provider,
        amount=subscription.amount,
        frequency=subscription.frequency,
        next_billing_date=subscription.next_billing_date,
        category=subscription.category,
        status=subscription.status,
        is_active=subscription.is_active,
        account_id=subscription.account_id,
        payment_account_id=subscription.payment_account_id,
        expense_account_id=subscription.expense_account_id,
        payment_journal_entry_id=subscription.payment_journal_entry_id,
        payment_reversal_journal_entry_id=subscription.payment_reversal_journal_entry_id,
        journal_entry_id=subscription.payment_journal_entry_id,
        reversal_journal_entry_id=subscription.payment_reversal_journal_entry_id,
        debit_account_id=subscription.expense_account_id,
        credit_account_id=subscription.payment_account_id,
        payment_amount=subscription.amount if subscription.payment_journal_entry_id else None,
        days_until_renewal=SubscriptionService.days_until_renewal(subscription),
        monthly_equivalent_amount=SubscriptionService.monthly_equivalent(subscription),
        yearly_equivalent_amount=SubscriptionService.yearly_equivalent(subscription),
        ai_detected=subscription.ai_detected,
        ai_recommendation=subscription.ai_recommendation,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


@router.post("", response_model=SubscriptionResponse)
async def create_subscription(
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a new subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.create(payload.model_dump())
    return _to_response(subscription)


@router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List subscriptions for the current tenant."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscriptions = await service.list_subscriptions(status=status)
    return [_to_response(s) for s in subscriptions]


@router.get("/active", response_model=list[SubscriptionResponse])
async def active_subscriptions(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Active subscriptions."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscriptions = await service.list_subscriptions(status="active")
    return [_to_response(s) for s in subscriptions]


@router.get("/cancelled", response_model=list[SubscriptionResponse])
async def cancelled_subscriptions(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancelled subscriptions."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscriptions = await service.list_subscriptions(status="cancelled")
    return [_to_response(s) for s in subscriptions]


@router.get("/upcoming-renewals", response_model=list[SubscriptionResponse])
async def upcoming_renewals(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Subscriptions renewing in the next 30 days."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscriptions = await service.list_subscriptions(status="active")
    upcoming = [s for s in subscriptions if (s.next_billing_date - date.today()).days <= 30]
    return [_to_response(s) for s in upcoming]


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _to_response(subscription)


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription = await service.update(subscription, payload.model_dump(exclude_unset=True))
    return _to_response(subscription)


@router.delete("/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Delete a subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await service.delete(subscription)
    return {"subscription_id": subscription_id, "deleted": True}


@router.post("/{subscription_id}/mark-paid", response_model=SubscriptionResponse)
async def mark_subscription_paid(
    subscription_id: int,
    payload: Optional[MarkPaidRequest] = None,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Record a subscription renewal as paid and post a journal entry."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    data = payload.model_dump(exclude_unset=True) if payload else {}
    try:
        subscription = await service.mark_paid(subscription, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(subscription)


@router.post("/{subscription_id}/mark-unpaid", response_model=SubscriptionResponse)
async def mark_subscription_unpaid(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Safely handle attempts to revert a paid subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        subscription = await service.mark_unpaid(subscription)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(subscription)


@router.post("/{subscription_id}/reverse-payment", response_model=SubscriptionResponse)
async def reverse_subscription_payment(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reverse the latest posted subscription payment without deleting journals."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    try:
        subscription = await service.reverse_payment(subscription)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(subscription)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel a subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription = await service.cancel(subscription)
    return _to_response(subscription)


@router.post("/{subscription_id}/pause", response_model=SubscriptionResponse)
async def pause_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Pause a subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription = await service.pause(subscription)
    return _to_response(subscription)


@router.post("/{subscription_id}/activate", response_model=SubscriptionResponse)
async def activate_subscription(
    subscription_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Activate/resume a subscription."""
    service = SubscriptionService(db, tenant_id=user.organization_id)
    subscription = await service.get(subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription = await service.activate(subscription)
    return _to_response(subscription)
