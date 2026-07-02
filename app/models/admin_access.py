from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin


class AdminAccessStatus(str, enum.Enum):
    """Status of a super-admin support access session."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AdminAccessSession(Base, TimestampMixin):
    """Auditable support access session for super admins.

    A super admin may start a support session for exactly one tenant
    (organization) at a time. The session records who accessed which tenant,
    why, when, and from where. It does NOT store any financial data.

    RLS is not applied to this table because it is a global audit log used
    to supervise support access itself.
    """
    __tablename__ = "admin_access_sessions"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    target_organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Required justification for the support access.
    reason = Column(Text, nullable=False)

    # Session timing.
    access_started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    access_expires_at = Column(DateTime, nullable=False)
    access_ended_at = Column(DateTime, nullable=True)

    # Request metadata for audit trail.
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(length=500), nullable=True)

    # Lifecycle status. Stored as a constrained string to avoid PostgreSQL
    # enum creation issues during migrations.
    status = Column(String(length=20), default=AdminAccessStatus.ACTIVE.value, nullable=False)

    # Relationships.
    admin_user = relationship("User", foreign_keys=[admin_user_id])
    target_organization = relationship("Organization", foreign_keys=[target_organization_id])
