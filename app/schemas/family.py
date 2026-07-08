"""Pydantic schemas for the family finance module."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.family import FamilyRole


class FamilyMemberBase(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    relationship_type: str = Field(..., min_length=1, max_length=50)
    role: FamilyRole = FamilyRole.VIEWER


class FamilyMemberCreate(FamilyMemberBase):
    user_id: Optional[int] = None


class FamilyMemberUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    relationship_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    role: Optional[FamilyRole] = None
    is_active: Optional[bool] = None


class FamilyMemberResponse(BaseModel):
    id: int
    family_id: int
    tenant_id: int
    user_id: Optional[int] = None
    email: str
    first_name: str
    last_name: str
    relationship_type: str
    role: str
    is_active: bool
    invitation_accepted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FamilyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    currency: str = Field(default="OMR", min_length=3, max_length=3)


class FamilyCreate(FamilyBase):
    pass


class FamilyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)


class FamilyResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    currency: str
    created_at: datetime
    updated_at: datetime
    members: List[FamilyMemberResponse] = []

    model_config = {"from_attributes": True}


class FamilyPermissionsResponse(BaseModel):
    role: str
    can_view_family: bool
    can_edit_family: bool
    can_manage_members: bool
    can_view_accounts: bool
    can_edit_transactions: bool
    can_view_reports: bool
    can_approve_purchases: bool
