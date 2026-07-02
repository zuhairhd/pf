from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class AdminAccessStartRequest(BaseModel):
    """Request body to start a super-admin support session."""
    target_organization_id: int = Field(..., gt=0, description="Tenant/organization to support")
    reason: str = Field(..., min_length=1, max_length=2000, description="Why support access is needed")
    expires_minutes: int = Field(default=30, ge=1, le=480, description="Session lifetime in minutes (max 8 hours)")


class AdminAccessEndRequest(BaseModel):
    """Request body to end a super-admin support session."""
    access_session_id: int = Field(..., gt=0)


class AdminAccessSessionResponse(BaseModel):
    """Response model for a support access session."""
    id: int
    admin_user_id: int
    target_organization_id: int
    reason: str
    access_started_at: datetime
    access_expires_at: datetime
    access_ended_at: Optional[datetime] = None
    status: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
