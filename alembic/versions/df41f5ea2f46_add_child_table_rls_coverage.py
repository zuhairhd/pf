"""Add child table RLS coverage

Revision ID: df41f5ea2f46
Revises: 4a2c8d1e5f6b
Create Date: 2026-07-02 09:20:44.264892

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'df41f5ea2f46'
down_revision: Union[str, Sequence[str], None] = '4a2c8d1e5f6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# GUC variable used for tenant context (must match app/core/rls.py)
TENANT_GUC = "app.current_tenant_id"

# Child tables that inherit tenancy from a parent table via foreign key.
# Format: table_name: (parent_table, parent_pk, child_fk)
CHILD_TABLES = {
    "ai_chat_messages": ("ai_chat_sessions", "id", "session_id"),
    "budget_categories": ("budgets", "id", "budget_id"),
    "credit_score_history": ("credit_profiles", "id", "credit_profile_id"),
    "goal_contributions": ("goals", "id", "goal_id"),
    "loan_payments": ("loans", "id", "loan_id"),
}

# Tables scoped by organization_id instead of tenant_id.
ORGANIZATION_SCOPED_TABLES = [
    "tenant_subscriptions",
]

# Index definitions for foreign key columns used in RLS joins.
CHILD_INDEXES = [
    ("ai_chat_messages", "session_id"),
    ("budget_categories", "budget_id"),
    ("credit_score_history", "credit_profile_id"),
    ("goal_contributions", "goal_id"),
    ("loan_payments", "loan_id"),
]


def _tenant_expr(tenant_id_type: str = "INTEGER") -> str:
    """Return the standard tenant_id matching expression."""
    return f"NULLIF(current_setting('{TENANT_GUC}', true), '')::{tenant_id_type}"


def _child_policy_expr(table: str, parent: str, parent_pk: str, child_fk: str) -> str:
    """Return an EXISTS-based RLS expression for a child table."""
    tenant_expr = _tenant_expr()
    return (
        f"EXISTS ("
        f"SELECT 1 FROM {parent} "
        f"WHERE {parent}.{parent_pk} = {table}.{child_fk} "
        f"AND {parent}.tenant_id = {tenant_expr}"
        f")"
    )


def _org_policy_expr(table: str) -> str:
    """Return an organization_id-based RLS expression."""
    return f"organization_id = {_tenant_expr()}"


def upgrade() -> None:
    """Enable RLS and create policies/indexes for child tenant tables."""

    # Add indexes on foreign key columns to make join-based RLS performant.
    for table, column in CHILD_INDEXES:
        op.create_index(
            op.f(f"ix_{table}_{column}"),
            table,
            [column],
            unique=False,
        )

    # Index on tenant_subscriptions.organization_id for RLS performance.
    op.create_index(
        op.f("ix_tenant_subscriptions_organization_id"),
        "tenant_subscriptions",
        ["organization_id"],
        unique=False,
    )

    # Enable and force RLS on child tables.
    for table in CHILD_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # Enable and force RLS on organization-scoped tables.
    for table in ORGANIZATION_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # Create child-table policies (SELECT/INSERT/UPDATE/DELETE).
    for table, (parent, parent_pk, child_fk) in CHILD_TABLES.items():
        expr = _child_policy_expr(table, parent, parent_pk, child_fk)
        prefix = f"rls_{table}"

        op.execute(f"""
            CREATE POLICY {prefix}_select ON {table}
            FOR SELECT
            USING ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_insert ON {table}
            FOR INSERT
            WITH CHECK ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_update ON {table}
            FOR UPDATE
            USING ({expr})
            WITH CHECK ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_delete ON {table}
            FOR DELETE
            USING ({expr})
        """)

    # Create organization-scoped policies.
    for table in ORGANIZATION_SCOPED_TABLES:
        expr = _org_policy_expr(table)
        prefix = f"rls_{table}"

        op.execute(f"""
            CREATE POLICY {prefix}_select ON {table}
            FOR SELECT
            USING ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_insert ON {table}
            FOR INSERT
            WITH CHECK ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_update ON {table}
            FOR UPDATE
            USING ({expr})
            WITH CHECK ({expr})
        """)

        op.execute(f"""
            CREATE POLICY {prefix}_delete ON {table}
            FOR DELETE
            USING ({expr})
        """)


def downgrade() -> None:
    """Remove child-table RLS policies, disable RLS, and drop indexes."""

    # Drop policies for organization-scoped tables.
    for table in ORGANIZATION_SCOPED_TABLES:
        prefix = f"rls_{table}"
        op.execute(f"DROP POLICY IF EXISTS {prefix}_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_delete ON {table}")

    # Drop policies for child tables.
    for table in CHILD_TABLES:
        prefix = f"rls_{table}"
        op.execute(f"DROP POLICY IF EXISTS {prefix}_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {prefix}_delete ON {table}")

    # Disable RLS on organization-scoped tables.
    for table in ORGANIZATION_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Disable RLS on child tables.
    for table in CHILD_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Drop organization_id index.
    op.drop_index(
        op.f("ix_tenant_subscriptions_organization_id"),
        table_name="tenant_subscriptions",
    )

    # Drop child-table FK indexes.
    for table, column in CHILD_INDEXES:
        op.drop_index(
            op.f(f"ix_{table}_{column}"),
            table_name=table,
        )
