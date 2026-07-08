"""API routes for family finance."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import User
from app.schemas.family import (
    FamilyCreate,
    FamilyResponse,
    FamilyUpdate,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
    FamilyPermissionsResponse,
)
from app.services.family_service import FamilyService, FamilyServiceError


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
