from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Audit trail for all significant actions."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    tenant_id = Column(Integer, nullable=False)
    action = Column(String(100), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN, EXPORT, etc.
    entity_type = Column(String(100), nullable=False)  # journal_entry, user, budget, etc.
    entity_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    changes_json = Column(Text, nullable=True)  # JSON diff of changes


class SystemEvent(Base, TimestampMixin):
    """System-level events (errors, warnings, info)."""
    __tablename__ = "system_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)  # error, warning, info, metric
    source = Column(String(100), nullable=False)  # service name
    message = Column(Text, nullable=False)
    details_json = Column(Text, nullable=True)
    severity = Column(String(20), default="info", nullable=False)
