"""PostgreSQL Row-Level Security helpers for tenant isolation.

This module provides functions to set, clear, and manage the tenant context
on database connections. The tenant context is stored as a PostgreSQL
configuration variable (app.current_tenant_id) and is used by RLS policies
to filter rows.

IMPORTANT: Always use SET LOCAL (not SET) to ensure the context is scoped
to the current transaction and does not leak across connection pool reuse.
"""

from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


# The PostgreSQL GUC (Grand Unified Configuration) variable name
TENANT_GUC = "app.current_tenant_id"


def _validate_tenant_id(tenant_id: Optional[int]) -> None:
    """Validate that tenant_id is a valid integer."""
    if tenant_id is None:
        return
    if not isinstance(tenant_id, int):
        raise ValueError(f"tenant_id must be an integer, got {type(tenant_id).__name__}")
    if tenant_id <= 0:
        raise ValueError(f"tenant_id must be a positive integer, got {tenant_id}")


async def set_tenant_context_async(
    session: AsyncSession,
    tenant_id: Optional[int],
) -> None:
    """Set the tenant context on an async SQLAlchemy session.

    Uses SET LOCAL so the context is scoped to the current transaction
    and is automatically cleared when the transaction ends.

    Args:
        session: The async SQLAlchemy session/connection.
        tenant_id: The tenant ID to set, or None to clear.
    """
    _validate_tenant_id(tenant_id)
    if tenant_id is not None:
        await session.execute(
            text(f"SET LOCAL {TENANT_GUC} = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )
    else:
        await session.execute(text(f"SET LOCAL {TENANT_GUC} = ''"))


def set_tenant_context_sync(
    session: Session,
    tenant_id: Optional[int],
) -> None:
    """Set the tenant context on a sync SQLAlchemy session.

    Uses SET LOCAL so the context is scoped to the current transaction.

    Args:
        session: The sync SQLAlchemy session/connection.
        tenant_id: The tenant ID to set, or None to clear.
    """
    _validate_tenant_id(tenant_id)
    if tenant_id is not None:
        session.execute(
            text(f"SET LOCAL {TENANT_GUC} = :tenant_id"),
            {"tenant_id": str(tenant_id)},
        )
    else:
        session.execute(text(f"SET LOCAL {TENANT_GUC} = ''"))


async def clear_tenant_context_async(session: AsyncSession) -> None:
    """Clear the tenant context on an async session."""
    await session.execute(text(f"SET LOCAL {TENANT_GUC} = ''"))


def clear_tenant_context_sync(session: Session) -> None:
    """Clear the tenant context on a sync session."""
    session.execute(text(f"SET LOCAL {TENANT_GUC} = ''"))


def get_rls_policy_sql(table_name: str, tenant_id_type: str = "INTEGER") -> str:
    """Generate the SQL expression for an RLS policy.

    The expression uses NULLIF to safely handle missing context:
    - If app.current_tenant_id is not set, it returns an empty string
    - NULLIF converts empty string to NULL
    - NULL compared to anything returns NULL (which RLS treats as "no access")
    - This prevents accidental access when tenant context is missing

    Args:
        table_name: The name of the table (used for policy naming).
        tenant_id_type: The SQL type of tenant_id (default INTEGER).

    Returns:
        The SQL expression string for the policy USING clause.
    """
    return (
        f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::{tenant_id_type}"
    )


# List of tables that should have RLS enabled (have tenant_id column)
# These are the tenant-scoped tables in the current schema.
TENANT_SCOPED_TABLES = [
    "accounts",
    "ai_chat_sessions",
    "ai_insights",
    "ai_reports",
    "ai_token_usage",
    "assets",
    "audit_logs",
    "bills",
    "budget_alerts",
    "budgets",
    "credit_profiles",
    "documents",
    "feature_usage",
    "goals",
    "investments",
    "journal_entries",
    "journal_lines",
    "loans",
    "notifications",
    "recurring_transactions",
    "subscriptions",
    "tax_payments",
    "tax_profiles",
    "user_activities",
]

# Tables that are global/shared and should NOT have RLS
# These tables either have no tenant_id or are system-level.
GLOBAL_TABLES = [
    "alembic_version",        # Migration tracking
    "organizations",          # The tenant table itself
    "users",                  # Cross-tenant user lookup (linked via org)
    "family_members",         # Linked to users
    "refresh_tokens",         # Auth system
    "email_verifications",    # Auth system
    "password_resets",        # Auth system
    "notification_settings",  # Per-user, not per-tenant
    "budget_categories",      # Child of budgets (RLS via parent)
    "goal_contributions",     # Child of goals (RLS via parent)
    "loan_payments",          # Child of loans (RLS via parent)
    "credit_score_history",   # Child of credit_profiles
    "system_events",          # System-level logging
    "tenant_subscriptions",   # Billing records
    "ai_chat_messages",       # Child of ai_chat_sessions (RLS via parent)
]
