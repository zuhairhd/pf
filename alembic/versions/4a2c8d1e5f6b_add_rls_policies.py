"""Add PostgreSQL Row-Level Security policies

Revision ID: 4a2c8d1e5f6b
Revises: 89b158bef60e
Create Date: 2026-07-01 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a2c8d1e5f6b'
down_revision: Union[str, Sequence[str], None] = '89b158bef60e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that have tenant_id and should be protected by RLS
# These are the tenant-scoped tables from app/core/rls.py
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

# The GUC variable name used for tenant context
TENANT_GUC = "app.current_tenant_id"


def upgrade() -> None:
    """Enable RLS and create policies for all tenant-scoped tables."""
    
    # For each tenant-scoped table:
    # 1. Enable RLS
    # 2. Force RLS (table owner also subject to RLS)
    # 3. Create SELECT policy
    # 4. Create INSERT policy (WITH CHECK)
    # 5. Create UPDATE policy (USING + WITH CHECK)
    # 6. Create DELETE policy
    
    for table in TENANT_SCOPED_TABLES:
        # Enable RLS on the table
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        
        # Force RLS so that table owner (the app user) is also subject to policies
        # This is critical because the app typically connects as the table owner
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        
        # Policy name prefix
        prefix = f"rls_{table}"
        
        # SELECT policy: users can only see rows from their tenant
        op.execute(f"""
            CREATE POLICY {prefix}_select ON {table}
            FOR SELECT
            USING (
                tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::INTEGER
            )
        """)
        
        # INSERT policy: users can only insert rows for their tenant
        op.execute(f"""
            CREATE POLICY {prefix}_insert ON {table}
            FOR INSERT
            WITH CHECK (
                tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::INTEGER
            )
        """)
        
        # UPDATE policy: users can only update rows from their tenant
        op.execute(f"""
            CREATE POLICY {prefix}_update ON {table}
            FOR UPDATE
            USING (
                tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::INTEGER
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::INTEGER
            )
        """)
        
        # DELETE policy: users can only delete rows from their tenant
        op.execute(f"""
            CREATE POLICY {prefix}_delete ON {table}
            FOR DELETE
            USING (
                tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::INTEGER
            )
        """)


def downgrade() -> None:
    """Remove RLS policies and disable RLS for all tenant-scoped tables."""
    
    for table in TENANT_SCOPED_TABLES:
        # Drop all policies on the table
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS rls_{table}_delete ON {table}")
        
        # Disable FORCE RLS
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        
        # Disable RLS
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
