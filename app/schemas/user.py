from pydantic import BaseModel, Field
from typing import Optional


class UserCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    theme: Optional[str] = None


class UserPreferenceUpdate(BaseModel):
    timezone: Optional[str] = None
    language: Optional[str] = None
    currency: Optional[str] = None
    theme: Optional[str] = None
    notification_preferences: Optional[dict] = None
