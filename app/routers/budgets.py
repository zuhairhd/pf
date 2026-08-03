from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User
from app.schemas.budget import BudgetCreate, FamilyBudgetCreate, FamilyBudgetResponse
from app.services.family_budget_service import FamilyBudgetService, FamilyBudgetServiceError

router = APIRouter()


def _budget_error_status(message: str) -> int:
    lower = message.lower()
    if "not found" in lower:
        return 404
    if "permission" in lower or "access" in lower:
        return 403
    return 400


async def _to_response(service: FamilyBudgetService, budget) -> FamilyBudgetResponse:
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
        can_manage=await service.can_user_manage_budget(budget),
    )


@router.get("/", response_model=list[FamilyBudgetResponse])
async def list_budgets(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """List budgets visible to the current user. Delegates to FamilyBudgetService."""
    service = FamilyBudgetService(db, tenant_id=user.organization_id, user=user)
    budgets = await service.list_visible_budgets_for_user()
    return [await _to_response(service, b) for b in budgets]


@router.post("/", response_model=FamilyBudgetResponse)
async def create_budget(
    payload: BudgetCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a simple private budget for the current user. Delegates to FamilyBudgetService.

    For visibility control (private/shared/family), use POST /family/budgets.
    """
    service = FamilyBudgetService(db, tenant_id=user.organization_id, user=user)
    family_payload = FamilyBudgetCreate(
        name=payload.name,
        period=payload.period,
        start_date=payload.start_date,
        end_date=payload.end_date,
        visibility="private",
        categories=payload.categories,
    )
    try:
        budget = await service.create_budget(family_payload)
    except FamilyBudgetServiceError as exc:
        raise HTTPException(status_code=_budget_error_status(exc.message), detail=exc.message)
    return await _to_response(service, budget)
