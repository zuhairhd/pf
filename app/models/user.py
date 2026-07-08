from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, SoftDeleteMixin


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(Base, TimestampMixin):
    """A user account."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    
    # Auth
    is_active = Column(Boolean, default=True, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    # 2FA
    totp_secret = Column(String(32), nullable=True)
    is_2fa_enabled = Column(Boolean, default=False, nullable=False)
    
    # Profile
    phone = Column(String(50), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    timezone = Column(String(50), default="UTC", nullable=False)
    language = Column(String(10), default="en", nullable=False)
    currency = Column(String(3), default="OMR", nullable=False)
    theme = Column(String(20), default="light", nullable=False)
    
    # Organization
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.OWNER, nullable=False)
    
    # Timestamps
    last_login_at = Column(DateTime, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    
    # Relationships
    organization = relationship("Organization", back_populates="users")
    family_members = relationship("FamilyMember", back_populates="user", lazy="selectin")


