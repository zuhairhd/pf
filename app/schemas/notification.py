from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class NotificationCreate(BaseModel):
    notification_type: str
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    ai_confidence: Optional[float] = None
    ai_action_url: Optional[str] = None


class NotificationSettingUpdate(BaseModel):
    in_app: Optional[bool] = None
    email: Optional[bool] = None
    push: Optional[bool] = None
    sms: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    notification_type: str
    title: str
    message: str
    channel: str
    status: str
    is_read: bool
    read_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferenceResponse(BaseModel):
    id: int
    user_id: int
    notification_type: str
    in_app: bool
    email: bool
    push: bool
    sms: bool
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    notification_type: str
    in_app: Optional[bool] = None
    email: Optional[bool] = None
    push: Optional[bool] = None
    sms: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class ReminderRunResponse(BaseModel):
    bills: dict
    subscriptions: dict
    total_created: int
    total_skipped: int


class TestEmailResponse(BaseModel):
    success: bool
    backend: str
    message_id: Optional[str] = None
    error: Optional[str] = None
