from pydantic import BaseModel, Field
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
