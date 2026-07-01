from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional, List


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    theme: Optional[str] = None


class UserPreferenceUpdate(BaseModel):
    notification_email: Optional[bool] = None
    notification_push: Optional[bool] = None
    daily_brief_time: Optional[str] = None  # HH:MM
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
