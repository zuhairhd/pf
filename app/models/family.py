from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin


class FamilyRole(str, enum.Enum):
    """Family member role defining permissions within a household."""
    HEAD = "head"
    PARENT = "parent"
    ADULT = "adult"
    TEEN = "teen"
    CHILD = "child"
    VIEWER = "viewer"


class Family(Base, TimestampMixin):
    """A family/household profile scoped to one tenant."""
    __tablename__ = "families"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    currency = Column(String(3), default="OMR", nullable=False)

    # Relationships
    members = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan", lazy="selectin")


class FamilyMember(Base, TimestampMixin):
    """A member of a family."""
    __tablename__ = "family_members"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    relationship_type = Column(String(50), nullable=False)  # spouse, child, parent, self, etc.
    role = Column(String(20), default=FamilyRole.VIEWER.value, nullable=False)

    # Invitation lifecycle
    invitation_token = Column(String(255), nullable=True)
    invitation_sent_at = Column(DateTime, nullable=True)
    invitation_accepted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)

    # Relationships
    family = relationship("Family", back_populates="members")
    user = relationship("User", back_populates="family_members")
