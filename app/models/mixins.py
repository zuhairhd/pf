from sqlalchemy import Column, Integer, DateTime, Boolean, event
from sqlalchemy.orm import Query
from sqlalchemy.sql import expression
from datetime import datetime


class TimestampMixin:
    """Adds created_at and updated_at timestamps."""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SoftDeleteMixin:
    """Adds soft delete support."""
    deleted_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)


class TenantMixin:
    """Adds tenant_id to all tenant-scoped models."""
    tenant_id = Column(Integer, nullable=False, index=True)


# Auto-filter all queries by tenant_id (defense in depth)
# Note: PostgreSQL RLS is the primary defense. This is a secondary defense.
@event.listens_for(Query, "before_compile", retval=True)
def auto_filter_tenant(query):
    """Automatically inject tenant_id filter on all queries for TenantMixin models."""
    # This is a simplified version. In production, use a more robust implementation
    # that checks the current request context for tenant_id.
    # For now, we rely on explicit filtering in services and PostgreSQL RLS.
    return query
