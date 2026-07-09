"""API routes for bills."""

from __future__ import annotations

from typing import Optional

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User
from app.schemas.bill_subscription import BillCreate, BillUpdate, BillResponse, MarkPaidRequest
from app.services.bill_subscription_service import BillService


router = APIRouter(prefix="/bills", tags=["Bills"])


def _bill_status(bill) -> str:
    if not bill.is_active:
        return "cancelled"
    if bill.is_paid:
        return "paid"
    if bill.due_date < date.today():
        return "overdue"
    return "upcoming"


def _to_response(bill) -> BillResponse:
    return BillResponse(
        id=bill.id,
        tenant_id=bill.tenant_id,
        name=bill.name,
        provider=bill.provider,
        typical_amount=bill.typical_amount,
        due_date=bill.due_date,
        frequency=bill.frequency,
        is_auto_pay=bill.is_auto_pay,
        payment_method=bill.payment_method,
        is_paid=bill.is_paid,
        paid_at=bill.paid_at,
        payment_account_id=bill.payment_account_id,
        expense_account_id=bill.expense_account_id,
        payment_journal_entry_id=bill.payment_journal_entry_id,
        payment_reversal_journal_entry_id=bill.payment_reversal_journal_entry_id,
        journal_entry_id=bill.payment_journal_entry_id,
        reversal_journal_entry_id=bill.payment_reversal_journal_entry_id,
        debit_account_id=bill.expense_account_id,
        credit_account_id=bill.payment_account_id,
        payment_amount=bill.typical_amount if bill.payment_journal_entry_id else None,
        status=_bill_status(bill),
        ai_predicted_amount=bill.ai_predicted_amount,
        ai_trend=bill.ai_trend,
        ai_alert=bill.ai_alert,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    )


@router.post("", response_model=BillResponse)
async def create_bill(
    payload: BillCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a new bill."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.create(payload.model_dump())
    return _to_response(bill)


@router.get("", response_model=list[BillResponse])
async def list_bills(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List bills for the current tenant, optionally filtered by status."""
    service = BillService(db, tenant_id=user.organization_id)
    bills = await service.list_bills(status=status)
    return [_to_response(b) for b in bills]


@router.get("/upcoming", response_model=list[BillResponse])
async def upcoming_bills(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Bills due in the next 7 days."""
    service = BillService(db, tenant_id=user.organization_id)
    bills = await service.list_bills(status="upcoming")
    return [_to_response(b) for b in bills]


@router.get("/overdue", response_model=list[BillResponse])
async def overdue_bills(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Overdue bills."""
    service = BillService(db, tenant_id=user.organization_id)
    bills = await service.list_bills(status="overdue")
    return [_to_response(b) for b in bills]


@router.get("/{bill_id}", response_model=BillResponse)
async def get_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single bill."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return _to_response(bill)


@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill(
    bill_id: int,
    payload: BillUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a bill."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill = await service.update(bill, payload.model_dump(exclude_unset=True))
    return _to_response(bill)


@router.delete("/{bill_id}")
async def delete_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Delete a bill."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    await service.delete(bill)
    return {"bill_id": bill_id, "deleted": True}


@router.post("/{bill_id}/mark-paid", response_model=BillResponse)
async def mark_bill_paid(
    bill_id: int,
    payload: Optional[MarkPaidRequest] = None,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a bill as paid and post a journal entry."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    data = payload.model_dump(exclude_unset=True) if payload else {}
    try:
        bill = await service.mark_paid(bill, data, user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(bill)


@router.post("/{bill_id}/mark-unpaid", response_model=BillResponse)
async def mark_bill_unpaid(
    bill_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Revert a bill to unpaid."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    try:
        bill = await service.mark_unpaid(bill)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _to_response(bill)


@router.post("/{bill_id}/cancel", response_model=BillResponse)
async def cancel_bill(
    bill_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel a bill."""
    service = BillService(db, tenant_id=user.organization_id)
    bill = await service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill = await service.cancel(bill)
    return _to_response(bill)
