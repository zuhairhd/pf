"""API routes for family finance."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models.database import get_db
from app.models import User, Account, JournalEntry
from app.schemas.auth import TokenResponse
from app.schemas.family import (
    FamilyCreate,
    FamilyResponse,
    FamilyUpdate,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
    FamilyPermissionsResponse,
    FamilyInvitationAcceptRequest,
    FamilyInvitationCreate,
    FamilyInvitationResponse,
)
from app.schemas.accounting import AccountResponse
from app.schemas.budget import (
    BudgetCategoryCreate,
    BudgetCategoryResponse,
    BudgetCategoryUpdate,
    BudgetSummaryResponse,
    FamilyBudgetCreate,
    FamilyBudgetResponse,
    FamilyBudgetUpdate,
)
from app.schemas.goal import (
    FamilyGoalCreate,
    FamilyGoalUpdate,
    GoalContributionCreate,
    GoalContributionReversalRequest,
    GoalResponse,
    GoalContributionResponse,
    GoalProgressResponse,
)
from app.schemas.family_chore import (
    AllowanceSummaryResponse,
    ChoreApprovalRequest,
    ChoreCompletionCreate,
    ChoreCompletionResponse,
    ChoreCreate,
    ChorePaymentPostRequest,
    ChorePaymentPostResponse,
    ChorePaymentReverseResponse,
    ChoreResponse,
    ChoreUpdate,
)
from app.services.auth_service import AuthService
from app.services.family_service import FamilyService, FamilyServiceError
from app.services.family_budget_service import FamilyBudgetService, FamilyBudgetServiceError
from app.services.family_chore_service import FamilyChoreService, FamilyChoreServiceError
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


def _to_invitation_response(invitation) -> FamilyInvitationResponse:
    return FamilyInvitationResponse(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        family_id=invitation.family_id,
        email=invitation.email,
        first_name=invitation.first_name,
        last_name=invitation.last_name,
        relationship_type=invitation.relationship_type,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        cancelled_at=invitation.cancelled_at,
        invited_by_user_id=invitation.invited_by_user_id,
        member_id=invitation.member_id,
        created_at=invitation.created_at,
        updated_at=invitation.updated_at,
    )


def _service(db: AsyncSession, user: User) -> FamilyService:
    return FamilyService(db, tenant_id=user.organization_id, user=user)


def _invitation_error_status(message: str) -> int:
    lower = message.lower()
    if "not found" in lower:
        return 404
    if "permission" in lower:
        return 403
    return 400


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


@router.post("/members/invitations", response_model=FamilyInvitationResponse)
async def create_family_member_invitation(
    payload: FamilyInvitationCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Invite a new family member by email (AUTH-305)."""
    service = _service(db, user)
    try:
        invitation = await service.create_invitation(payload.model_dump())
    except FamilyServiceError as exc:
        raise HTTPException(status_code=_invitation_error_status(exc.message), detail=exc.message)
    return _to_invitation_response(invitation)


@router.get("/members/invitations", response_model=list[FamilyInvitationResponse])
async def list_family_member_invitations(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List invitations for the current tenant's family."""
    service = _service(db, user)
    invitations = await service.list_invitations()
    return [_to_invitation_response(i) for i in invitations]


@router.post("/members/invitations/{invitation_id}/cancel", response_model=FamilyInvitationResponse)
async def cancel_family_member_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel a pending family member invitation."""
    service = _service(db, user)
    try:
        invitation = await service.cancel_invitation(invitation_id)
    except FamilyServiceError as exc:
        raise HTTPException(status_code=_invitation_error_status(exc.message), detail=exc.message)
    return _to_invitation_response(invitation)


@router.post("/members/invitations/accept", response_model=TokenResponse)
async def accept_family_member_invitation(
    payload: FamilyInvitationAcceptRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept a family invitation: create the invited user's account, log
    them in, and activate their family membership.

    Unauthenticated by design (like /auth/register and /auth/reset-password)
    -- the bearer token itself proves the invitation is legitimate, and the
    resulting tenant is derived entirely from the token, not supplied by the
    caller, so there is no cross-tenant parameter to reject.
    """
    auth_service = AuthService(db)
    try:
        user = await auth_service.accept_family_invitation(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await auth_service.create_tokens(user)


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
        source_account_id=contribution.source_account_id,
        destination_account_id=contribution.destination_account_id,
        journal_entry_id=contribution.journal_entry_id,
        posting_status=contribution.posting_status,
        reversal_journal_entry_id=contribution.reversal_journal_entry_id,
        reversed_at=contribution.reversed_at,
        reversed_by_user_id=contribution.reversed_by_user_id,
        reversal_reason=contribution.reversal_reason,
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
        msg = exc.message.lower()
        if "not found" in msg:
            status_code = 404
        elif "permission" in msg or "access" in msg or "not allowed" in msg:
            status_code = 403
        else:
            status_code = 400
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


@router.get("/goals/{goal_id}/contributions/{contribution_id}", response_model=GoalContributionResponse)
async def get_goal_contribution(
    goal_id: int,
    contribution_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single family goal contribution."""
    service = _goal_service(db, user)
    try:
        contribution = await service.get_contribution(goal_id, contribution_id)
    except FamilyGoalServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_contribution_response(contribution)


@router.post("/goals/{goal_id}/contributions/{contribution_id}/post", response_model=GoalContributionResponse)
async def post_goal_contribution_to_accounting(
    goal_id: int,
    contribution_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Post an existing family goal contribution through the accounting engine."""
    service = _goal_service(db, user)
    try:
        contribution = await service.post_contribution_to_accounting(goal_id, contribution_id)
    except FamilyGoalServiceError as exc:
        msg = exc.message.lower()
        if "not found" in msg:
            status_code = 404
        elif "permission" in msg or "access" in msg or "not allowed" in msg:
            status_code = 403
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_contribution_response(contribution)


@router.post(
    "/goals/{goal_id}/contributions/{contribution_id}/reverse",
    response_model=GoalContributionResponse,
)
async def reverse_goal_contribution(
    goal_id: int,
    contribution_id: int,
    payload: GoalContributionReversalRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reverse a posted family goal contribution's journal entry."""
    service = _goal_service(db, user)
    try:
        contribution = await service.reverse_contribution(
            goal_id,
            contribution_id,
            reason=payload.reason,
            reversal_date=payload.reversal_date,
        )
    except FamilyGoalServiceError as exc:
        msg = exc.message.lower()
        if "not found" in msg:
            status_code = 404
        elif "permission" in msg or "access" in msg or "not allowed" in msg:
            status_code = 403
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=exc.message)
    return _to_contribution_response(contribution)


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


# ---------------------------------------------------------------------------
# Family Budgets (FAM-1303)
# ---------------------------------------------------------------------------


def _budget_service(db: AsyncSession, user: User) -> FamilyBudgetService:
    return FamilyBudgetService(db, tenant_id=user.organization_id, user=user)


def _budget_error_status(message: str) -> int:
    lower = message.lower()
    if "not found" in lower:
        return 404
    if "permission" in lower or "access" in lower:
        return 403
    return 400


async def _to_budget_response(
    service: FamilyBudgetService, budget, *, can_manage: Optional[bool] = None
) -> FamilyBudgetResponse:
    return FamilyBudgetResponse(
        id=budget.id,
        tenant_id=budget.tenant_id,
        family_id=budget.family_id,
        owner_user_id=budget.owner_user_id,
        created_by_user_id=budget.created_by_user_id,
        name=budget.name,
        period=budget.period.value if hasattr(budget.period, "value") else budget.period,
        start_date=budget.start_date,
        end_date=budget.end_date,
        currency=budget.currency,
        visibility=budget.visibility,
        status=budget.status,
        is_active=budget.is_active,
        total_budgeted=budget.total_budgeted,
        total_actual=budget.total_actual,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
        can_view=True,
        can_manage=can_manage if can_manage is not None else await service.can_user_manage_budget(budget),
    )


@router.post("/budgets", response_model=FamilyBudgetResponse)
async def create_family_budget(
    payload: FamilyBudgetCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a family-aware budget (private, shared, or family-wide)."""
    service = _budget_service(db, user)
    try:
        budget = await service.create_budget(payload)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.get("/budgets", response_model=list[FamilyBudgetResponse])
async def list_family_budgets(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List budgets the current user is allowed to see."""
    service = _budget_service(db, user)
    budgets = await service.list_visible_budgets_for_user()
    return [await _to_budget_response(service, b) for b in budgets]


@router.get("/budgets/{budget_id}", response_model=FamilyBudgetResponse)
async def get_family_budget(
    budget_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single budget if the user is allowed to view it."""
    service = _budget_service(db, user)
    try:
        budget = await service.get_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.patch("/budgets/{budget_id}", response_model=FamilyBudgetResponse)
async def update_family_budget(
    budget_id: int,
    payload: FamilyBudgetUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a budget's name, period, visibility, or status."""
    service = _budget_service(db, user)
    try:
        budget = await service.update_budget(budget_id, payload)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.post("/budgets/{budget_id}/archive", response_model=FamilyBudgetResponse)
async def archive_family_budget(
    budget_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Archive a budget (soft-close; does not delete history)."""
    service = _budget_service(db, user)
    try:
        budget = await service.archive_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.get("/budgets/{budget_id}/summary", response_model=BudgetSummaryResponse)
async def get_family_budget_summary(
    budget_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return a read-only budget-vs-actual summary computed from posted journal entries."""
    service = _budget_service(db, user)
    try:
        summary = await service.calculate_budget_summary(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return BudgetSummaryResponse(
        budget=await _to_budget_response(service, summary["budget"]),
        categories=[BudgetCategoryResponse(**c) for c in summary["categories"]],
        total_planned=summary["total_planned"],
        total_actual=summary["total_actual"],
        total_remaining=summary["total_remaining"],
        percent_used=summary["percent_used"],
        currency=summary["currency"],
        over_budget_category_ids=summary["over_budget_category_ids"],
        near_limit_category_ids=summary["near_limit_category_ids"],
    )


@router.post("/budgets/{budget_id}/categories", response_model=FamilyBudgetResponse)
async def create_family_budget_category(
    budget_id: int,
    payload: BudgetCategoryCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Add a category to a budget, linked to an expense account the user can access."""
    service = _budget_service(db, user)
    try:
        await service.create_budget_category(budget_id, payload)
        budget = await service.get_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.patch(
    "/budgets/{budget_id}/categories/{category_id}", response_model=FamilyBudgetResponse
)
async def update_family_budget_category(
    budget_id: int,
    category_id: int,
    payload: BudgetCategoryUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a budget category."""
    service = _budget_service(db, user)
    try:
        await service.update_budget_category(budget_id, category_id, payload)
        budget = await service.get_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


@router.delete("/budgets/{budget_id}/categories/{category_id}", response_model=FamilyBudgetResponse)
async def delete_family_budget_category(
    budget_id: int,
    category_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Remove a category from a budget."""
    service = _budget_service(db, user)
    try:
        await service.delete_budget_category(budget_id, category_id)
        budget = await service.get_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_budget_response(service, budget)


# ---------------------------------------------------------------------------
# Family Chores and Allowance Tracking (FAM-1304)
# ---------------------------------------------------------------------------


def _chore_service(db: AsyncSession, user: User) -> FamilyChoreService:
    return FamilyChoreService(db, tenant_id=user.organization_id, user=user)


def _chore_error_status(message: str) -> int:
    lower = message.lower()
    if "not found" in lower:
        return 404
    if "permission" in lower:
        return 403
    return 400


async def _to_chore_response(service: FamilyChoreService, chore) -> ChoreResponse:
    return ChoreResponse(
        id=chore.id,
        tenant_id=chore.tenant_id,
        family_id=chore.family_id,
        title=chore.title,
        description=chore.description,
        assigned_to_member_id=chore.assigned_to_member_id,
        created_by_user_id=chore.created_by_user_id,
        allowance_amount=chore.allowance_amount,
        currency=chore.currency,
        frequency=chore.frequency,
        due_date=chore.due_date,
        status=chore.status,
        requires_approval=chore.requires_approval,
        created_at=chore.created_at,
        updated_at=chore.updated_at,
        can_view=True,
        can_manage=await service.can_user_manage_chore(chore),
        can_submit_completion=await service.can_user_submit_completion(chore),
    )


def _to_completion_response(completion) -> ChoreCompletionResponse:
    return ChoreCompletionResponse(
        id=completion.id,
        tenant_id=completion.tenant_id,
        chore_id=completion.chore_id,
        family_id=completion.family_id,
        completed_by_member_id=completion.completed_by_member_id,
        completed_at=completion.completed_at,
        submitted_notes=completion.submitted_notes,
        status=completion.status,
        approved_by_user_id=completion.approved_by_user_id,
        approved_at=completion.approved_at,
        rejection_reason=completion.rejection_reason,
        earned_amount=completion.earned_amount,
        payment_status=completion.payment_status,
        payment_account_id=completion.payment_account_id,
        expense_account_id=completion.expense_account_id,
        payment_journal_entry_id=completion.payment_journal_entry_id,
        payment_reversal_journal_entry_id=completion.payment_reversal_journal_entry_id,
        paid_at=completion.paid_at,
        paid_by_user_id=completion.paid_by_user_id,
        created_at=completion.created_at,
        updated_at=completion.updated_at,
    )


@router.post("/chores", response_model=ChoreResponse)
async def create_family_chore(
    payload: ChoreCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a chore. Requires HEAD or PARENT."""
    service = _chore_service(db, user)
    try:
        chore = await service.create_chore(payload)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return await _to_chore_response(service, chore)


@router.get("/chores", response_model=list[ChoreResponse])
async def list_family_chores(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List chores the current user is allowed to see."""
    service = _chore_service(db, user)
    chores = await service.list_visible_chores_for_user()
    return [await _to_chore_response(service, c) for c in chores]


@router.get("/chores/{chore_id}", response_model=ChoreResponse)
async def get_family_chore(
    chore_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single chore if the user is allowed to view it."""
    service = _chore_service(db, user)
    try:
        chore = await service.get_chore(chore_id)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return await _to_chore_response(service, chore)


@router.patch("/chores/{chore_id}", response_model=ChoreResponse)
async def update_family_chore(
    chore_id: int,
    payload: ChoreUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update a chore. Requires HEAD or PARENT."""
    service = _chore_service(db, user)
    try:
        chore = await service.update_chore(chore_id, payload)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return await _to_chore_response(service, chore)


@router.post("/chores/{chore_id}/archive", response_model=ChoreResponse)
async def archive_family_chore(
    chore_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Archive a chore. Requires HEAD or PARENT."""
    service = _chore_service(db, user)
    try:
        chore = await service.archive_chore(chore_id)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return await _to_chore_response(service, chore)


@router.post("/chores/{chore_id}/completions", response_model=ChoreCompletionResponse)
async def submit_family_chore_completion(
    chore_id: int,
    payload: ChoreCompletionCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Submit a completion for a chore assigned to the current user."""
    service = _chore_service(db, user)
    try:
        completion = await service.submit_completion(chore_id, payload)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return _to_completion_response(completion)


@router.get("/chores/{chore_id}/completions", response_model=list[ChoreCompletionResponse])
async def list_family_chore_completions(
    chore_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List completions submitted for a chore."""
    service = _chore_service(db, user)
    try:
        completions = await service.list_completions(chore_id)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return [_to_completion_response(c) for c in completions]


@router.post("/chore-completions/{completion_id}/approve", response_model=ChoreCompletionResponse)
async def approve_family_chore_completion(
    completion_id: int,
    payload: ChoreApprovalRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Approve a chore completion. Requires HEAD or PARENT."""
    service = _chore_service(db, user)
    try:
        completion = await service.approve_completion(completion_id, earned_amount=payload.earned_amount)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return _to_completion_response(completion)


@router.post("/chore-completions/{completion_id}/reject", response_model=ChoreCompletionResponse)
async def reject_family_chore_completion(
    completion_id: int,
    payload: ChoreApprovalRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reject a chore completion with a reason. Requires HEAD or PARENT."""
    service = _chore_service(db, user)
    try:
        completion = await service.reject_completion(
            completion_id, rejection_reason=payload.rejection_reason or ""
        )
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    return _to_completion_response(completion)


@router.post("/chore-completions/{completion_id}/post-payment", response_model=ChorePaymentPostResponse)
async def post_family_chore_payment(
    completion_id: int,
    payload: ChorePaymentPostRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Post an approved allowance completion as a balanced journal entry.

    Requires HEAD or PARENT. Idempotent: calling this again after the
    completion is already paid returns the existing payment, without
    creating a duplicate journal entry.
    """
    service = _chore_service(db, user)
    try:
        completion = await service.post_payment(
            completion_id,
            payment_account_id=payload.payment_account_id,
            expense_account_id=payload.expense_account_id,
            payment_date=payload.payment_date,
            notes=payload.notes,
        )
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)
    chore = await service._get_chore_raw(completion.chore_id)
    return ChorePaymentPostResponse(
        completion_id=completion.id,
        payment_status=completion.payment_status,
        paid_at=completion.paid_at,
        payment_journal_entry_id=completion.payment_journal_entry_id,
        debit_account_id=completion.expense_account_id,
        credit_account_id=completion.payment_account_id,
        amount=completion.earned_amount,
        currency=chore.currency if chore is not None else "OMR",
    )


@router.post("/chore-completions/{completion_id}/reverse-payment", response_model=ChorePaymentReverseResponse)
async def reverse_family_chore_payment(
    completion_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reverse a posted allowance payment through the accounting engine.

    Requires HEAD or PARENT. Idempotent: calling this again after the
    payment is already reversed returns the existing reversal, without
    creating a duplicate reversing journal entry. The original payment
    journal entry is never deleted or mutated.
    """
    service = _chore_service(db, user)
    try:
        completion = await service.reverse_payment(completion_id)
    except FamilyChoreServiceError as exc:
        raise HTTPException(status_code=_chore_error_status(exc.message), detail=exc.message)

    reversed_at = None
    if completion.payment_journal_entry_id:
        original = await db.execute(
            select(JournalEntry).where(
                JournalEntry.id == completion.payment_journal_entry_id,
                JournalEntry.tenant_id == user.organization_id,
            )
        )
        original_entry = original.scalar_one_or_none()
        reversed_at = original_entry.reversed_at if original_entry is not None else None

    return ChorePaymentReverseResponse(
        completion_id=completion.id,
        payment_status=completion.payment_status,
        payment_journal_entry_id=completion.payment_journal_entry_id,
        payment_reversal_journal_entry_id=completion.payment_reversal_journal_entry_id,
        reversed_at=reversed_at,
    )


@router.get("/allowance-summary", response_model=AllowanceSummaryResponse)
async def get_family_allowance_summary(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return a read-only allowance summary scoped to the current user's role."""
    service = _chore_service(db, user)
    summary = await service.get_allowance_summary()
    return AllowanceSummaryResponse(**summary)
