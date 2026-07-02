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
        # asyncpg does not accept bound parameters in a SET statement, so the
        # validated integer is inlined safely as a quoted string literal.
        await session.execute(text(f"SET LOCAL {TENANT_GUC} = '{tenant_id}'"))
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

# Child tables that do NOT have a direct tenant_id column but are
# tenant-scoped through a parent table that has RLS. These receive
# join-based RLS policies using EXISTS(...) to the parent.
CHILD_TABLES = {
    # table_name: (parent_table, parent_pk, child_fk)
    "ai_chat_messages": ("ai_chat_sessions", "id", "session_id"),
    "budget_categories": ("budgets", "id", "budget_id"),
    "credit_score_history": ("credit_profiles", "id", "credit_profile_id"),
    "goal_contributions": ("goals", "id", "goal_id"),
    "loan_payments": ("loans", "id", "loan_id"),
}

# Tenant-level tables that use organization_id as the tenant identifier
# instead of a tenant_id column. These receive RLS policies keyed on
# organization_id, matching the current tenant context GUC.
ORGANIZATION_SCOPED_TABLES = [
    "tenant_subscriptions",
]

# Tables that are global/shared and should NOT have RLS.
# These tables either have no tenant_id, are system-level, or are
# auth/user-scoped and require cross-tenant lookup before tenant context
# can be established.
GLOBAL_TABLES = [
    "alembic_version",        # Alembic internal migration tracking
    "organizations",          # The tenant table itself
    "users",                  # Auth lookup by email; app-level org filtering
    "family_members",         # User-scoped (app-level user filtering)
    "refresh_tokens",         # Auth system
    "email_verifications",    # Auth system
    "password_resets",        # Auth system
    "notification_settings",  # Per-user preferences (app-level user filtering)
    "system_events",          # System-level logging
]


def get_child_rls_policy_sql(
    table_name: str,
    parent_table: str,
    parent_pk: str,
    child_fk: str,
    tenant_id_type: str = "INTEGER",
) -> str:
    """Generate an EXISTS-based RLS expression for a child table.

    The expression checks that the referenced parent row belongs to the
    current tenant. Used for tables that inherit tenancy from a parent.
    """
    return (
        f"EXISTS ("
        f"SELECT 1 FROM {parent_table} "
        f"WHERE {parent_table}.{parent_pk} = {table_name}.{child_fk} "
        f"AND {parent_table}.tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::{tenant_id_type}"
        f")"
    )


def get_organization_rls_policy_sql(
    table_name: str,
    tenant_id_type: str = "INTEGER",
) -> str:
    """Generate an RLS expression for a table scoped by organization_id."""
    return (
        f"organization_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::{tenant_id_type}"
    )
