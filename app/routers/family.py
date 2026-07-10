"""API routes for family finance."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User, Account
from app.schemas.family import (
    FamilyCreate,
    FamilyResponse,
    FamilyUpdate,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
    FamilyPermissionsResponse,
)
from app.schemas.accounting import AccountResponse
from app.schemas.goal import (
    FamilyGoalCreate,
    FamilyGoalUpdate,
    GoalContributionCreate,
    GoalResponse,
    GoalContributionResponse,
    GoalProgressResponse,
)
from app.services.family_service import FamilyService, FamilyServiceError
from app.services.family_goal_service import FamilyGoalService, FamilyGoalServiceError
from app.services.family_account_access_service import FamilyAccountAccessService


router = APIRouter(prefix="/family", tags=["Family"])


def _to_family_response(family) -> FamilyResponse:
    return FamilyResponse(
        id=family.id,
        tenant_id=family.tenant_id,
        name=family.name,
        currency=family.currency,
        created_at=family.created_at,
        updated_at=family.updated_at,
        members=[_to_member_response(m) for m in family.members],
    )


def _to_member_response(member) -> FamilyMemberResponse:
    return FamilyMemberResponse(
        id=member.id,
        family_id=member.family_id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        email=member.email,
        first_name=member.first_name,
        last_name=member.last_name,
        relationship_type=member.relationship_type,
        role=member.role,
        is_active=member.is_active,
        invitation_accepted_at=member.invitation_accepted_at,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def _service(db: AsyncSession, user: User) -> FamilyService:
    return FamilyService(db, tenant_id=user.organization_id, user=user)


@router.post("", response_model=FamilyResponse)
async def create_family(
    payload: FamilyCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a family profile for the current tenant."""
    service = _service(db, user)
    try:
        family = await service.create_family(payload.model_dump())
    except FamilyServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return _to_family_response(family)


@router.get("", response_model=Optional[FamilyResponse])
async def get_family(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get the family profile for the current tenant."""
    service = _service(db, user)
    family = await service.get_family()
    if family is None:
        return None
    return _to_family_response(family)


@router.patch("", response_model=FamilyResponse)
async def update_family(
    payload: FamilyUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update the family profile."""
    service = _service(db, user)
    family = await service.get_family()
    if family is None:
        raise HTTPException(status_code=404, detail="Family profile not found")
    try:
        await service.require_permission("can_edit_family")
    except FamilyServiceError as exc:
        raise HTTPException(status_code=403, detail=exc.message)
    family = await service.update_family(family, payload.model_dump(exclude_unset=True))
    return _to_family_response(family)


@router.post("/members", response_model=FamilyMemberResponse)
async def create_family_member(
    payload: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Add a member to the family."""
    service = _service(db, user)
    try:
        await service.require_permission("can_manage_members")
        member = await service.create_member(payload.model_dump())
    except FamilyServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return _to_member_response(member)


@router.get("/members", response_model=list[FamilyMemberResponse])
async def list_family_members(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List members of the current tenant's family."""
    service = _service(db, user)
    members = await service.list_members()
    return [_to_member_response(m) for m in members]


@router.patch("/members/{member_id}", response_model=FamilyMemberResponse)
async def update_family_member(
    member_id: int,
    payload: FamilyMemberUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a family member."""
    service = _service(db, user)
    member = await service.get_member(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Family member not found")
    try:
        await service.require_permission("can_manage_members")
        member = await service.update_member(member, payload.model_dump(exclude_unset=True))
    except FamilyServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return _to_member_response(member)


@router.delete("/members/{member_id}")
async def delete_family_member(
    member_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Remove a family member."""
    service = _service(db, user)
    member = await service.get_member(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Family member not found")
    try:
        await service.require_permission("can_manage_members")
        await service.delete_member(member)
    except FamilyServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return {"member_id": member_id, "deleted": True}


@router.get("/permissions", response_model=FamilyPermissionsResponse)
async def get_family_permissions(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the current user's family permissions."""
    service = _service(db, user)
    perms = await service.get_permissions()
    return FamilyPermissionsResponse(**perms)


def _to_account_response(account: Account) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        tenant_id=account.tenant_id,
        code=account.code,
        name=account.name,
        account_type=account.account_type,
        parent_account_id=account.parent_account_id,
        description=account.description,
        is_active=account.is_active,
        is_bank_account=account.is_bank_account,
        is_cash_account=account.is_cash_account,
        is_credit_card=account.is_credit_card,
        visibility=account.visibility,
        owner_user_id=account.owner_user_id,
        family_id=account.family_id,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/accounts/visible", response_model=list[AccountResponse])
async def list_visible_family_accounts(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List accounts the current user is allowed to see."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    accounts = await access.list_visible_accounts()
    return [_to_account_response(a) for a in accounts]


async def _get_manageable_account(
    account_id: int,
    db: AsyncSession,
    user: User,
) -> Account:
    """Fetch an account and enforce family management permission."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    result = await db.execute(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == user.organization_id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not await access.can_manage_account(account):
        raise HTTPException(status_code=403, detail="Access denied")
    return account


@router.post("/accounts/{account_id}/share", response_model=AccountResponse)
async def share_family_account(
    account_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Make an account shared with the family."""
    account = await _get_manageable_account(account_id, db, user)
    account.visibility = "shared"
    await db.commit()
    await db.refresh(account)
    return _to_account_response(account)


@router.post("/accounts/{account_id}/make-private", response_model=AccountResponse)
async def make_family_account_private(
    account_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Make an account private. Ownership falls to the current user if unset."""
    account = await _get_manageable_account(account_id, db, user)
    account.visibility = "private"
    if account.owner_user_id is None:
        account.owner_user_id = user.id
    await db.commit()
    await db.refresh(account)
    return _to_account_response(account)


# ---------------------------------------------------------------------------
# Family goals
# ---------------------------------------------------------------------------


def _goal_service(db: AsyncSession, user: User) -> FamilyGoalService:
    return FamilyGoalService(db, tenant_id=user.organization_id, user=user)


def _to_goal_response(goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        tenant_id=goal.tenant_id,
        family_id=goal.family_id,
        owner_user_id=goal.owner_user_id,
        name=goal.name,
        goal_type=goal.goal_type.value if hasattr(goal.goal_type, "value") else goal.goal_type,
        status=goal.status.value if hasattr(goal.status, "value") else goal.status,
        visibility=goal.visibility,
        target_amount=goal.target_amount,
        current_amount=goal.current_amount,
        target_date=goal.target_date,
        monthly_contribution=goal.monthly_contribution,
        description=goal.description,
        priority=goal.priority,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def _to_contribution_response(contribution) -> GoalContributionResponse:
    return GoalContributionResponse(
        id=contribution.id,
        goal_id=contribution.goal_id,
        tenant_id=contribution.tenant_id,
        amount=contribution.amount,
        date=contribution.date,
        source=contribution.source,
        description=contribution.description,
        contributed_by_user_id=contribution.contributed_by_user_id,
        account_id=contribution.account_id,
        created_at=contribution.created_at,
        updated_at=contribution.updated_at,
    )


@router.post("/goals", response_model=GoalResponse)
async def create_family_goal(
    payload: FamilyGoalCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a family-scoped goal."""
    service = _goal_service(db, user)
    try:
        goal = await service.create_family_goal(payload)
    except FamilyGoalServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message)
    return _to_goal_response(goal)


@router.get("/goals", response_model=list[GoalResponse])
async def list_family_goals(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List goals the current user is allowed to see."""
    service = _goal_service(db, user)
    goals = await service.list_visible_goals()
    return [_to_goal_response(g) for g in goals]


@router.get("/goals/{goal_id}", response_model=GoalResponse)
async def get_family_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single family goal if the user is allowed to view it."""
    service = _goal_service(db, user)
    try:
        goal = await service.get_goal(goal_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_goal_response(goal)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_family_goal(
    goal_id: int,
    payload: FamilyGoalUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a family goal."""
    service = _goal_service(db, user)
    try:
        goal = await service.update_goal(goal_id, payload)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_goal_response(goal)


@router.post("/goals/{goal_id}/cancel", response_model=GoalResponse)
async def cancel_family_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel a family goal."""
    service = _goal_service(db, user)
    try:
        goal = await service.cancel_goal(goal_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_goal_response(goal)


@router.post("/goals/{goal_id}/complete", response_model=GoalResponse)
async def complete_family_goal(
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a family goal as completed."""
    service = _goal_service(db, user)
    try:
        goal = await service.complete_goal(goal_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_goal_response(goal)


@router.post("/goals/{goal_id}/contributions", response_model=GoalContributionResponse)
async def add_goal_contribution(
    goal_id: int,
    payload: GoalContributionCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Add a contribution to a family goal."""
    service = _goal_service(db, user)
    try:
        contribution = await service.add_contribution(goal_id, payload)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_contribution_response(contribution)


@router.get("/goals/{goal_id}/contributions", response_model=list[GoalContributionResponse])
async def list_goal_contributions(
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List contributions for a family goal."""
    service = _goal_service(db, user)
    try:
        contributions = await service.list_contributions(goal_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return [_to_contribution_response(c) for c in contributions]


@router.get("/goals/{goal_id}/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get progress details for a family goal."""
    service = _goal_service(db, user)
    try:
        progress = await service.get_progress(goal_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return GoalProgressResponse(
        goal=_to_goal_response(progress["goal"]),
        target=progress["target"],
        current=progress["current"],
        remaining=progress["remaining"],
        progress_percentage=progress["progress_percentage"],
        monthly_contribution=progress["monthly_contribution"],
        months_to_completion=progress["months_to_completion"],
        estimated_completion=progress["estimated_completion"],
        contributions=[_to_contribution_response(c) for c in progress["contributions"]],
        is_on_track=progress["is_on_track"],
    )
