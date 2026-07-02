"""PostgreSQL RLS child-table isolation tests.

These tests verify that tenant-related child tables without a direct
tenant_id column are still isolated by PostgreSQL RLS through their
parent relationships.

The tests run against the real database configured in DATABASE_URL,
but they only create and delete synthetic test rows.
"""

import os
import uuid
from datetime import date, datetime

from dotenv import load_dotenv
import pytest
from sqlalchemy import create_engine, text

# Load environment from project .env so tests use the same database URL
# the application uses. This file is ignored by git and must never be committed.
load_dotenv(dotenv_path=".env")

# Use the same database credentials the application uses.
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

SYNC_URL = DATABASE_URL.replace("+asyncpg", "")
engine = create_engine(SYNC_URL)


def _unique(prefix: str) -> str:
    """Generate a unique string for test data to avoid collisions."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestRLSChildTables:
    """RLS isolation tests for child tables."""

    @pytest.fixture(autouse=True)
    def setup_and_cleanup(self):
        """Create two tenants with parent/child rows, yield, then clean up."""
        self.run_id = uuid.uuid4().hex[:8]
        self.tenant_a = 900001
        self.tenant_b = 900002
        self.user_a_email = f"user_a_{self.run_id}@example.com"
        self.user_b_email = f"user_b_{self.run_id}@example.com"

        with engine.connect() as conn:
            # Create two tenant organizations.
            org_a_slug = _unique("tenant-a")
            org_b_slug = _unique("tenant-b")
            conn.execute(
                text("""
                    INSERT INTO organizations
                    (id, name, slug, is_active, plan, status, max_users, max_transactions,
                     max_ai_requests_per_day, max_storage_mb, created_at, updated_at)
                    VALUES
                    (:id_a, :name_a, :slug_a, true, 'FREE', 'ACTIVE', 1, 100, 5, 100, NOW(), NOW()),
                    (:id_b, :name_b, :slug_b, true, 'FREE', 'ACTIVE', 1, 100, 5, 100, NOW(), NOW())
                """),
                {
                    "id_a": self.tenant_a,
                    "name_a": f"Tenant A {self.run_id}",
                    "slug_a": org_a_slug,
                    "id_b": self.tenant_b,
                    "name_b": f"Tenant B {self.run_id}",
                    "slug_b": org_b_slug,
                },
            )

            # Create one user per tenant.
            conn.execute(
                text("""
                    INSERT INTO users
                    (email, hashed_password, first_name, last_name, is_active,
                     is_email_verified, is_superuser, is_2fa_enabled, organization_id, role, timezone, language,
                     currency, theme, created_at, updated_at)
                    VALUES
                    (:email_a, 'hash', 'First', 'User', true, true, false, false, :org_a, 'OWNER', 'UTC', 'en', 'OMR', 'light', NOW(), NOW()),
                    (:email_b, 'hash', 'Second', 'User', true, true, false, false, :org_b, 'OWNER', 'UTC', 'en', 'OMR', 'light', NOW(), NOW())
                """),
                {
                    "email_a": self.user_a_email,
                    "org_a": self.tenant_a,
                    "email_b": self.user_b_email,
                    "org_b": self.tenant_b,
                },
            )
            user_a_id, user_b_id = conn.execute(
                text("SELECT id FROM users WHERE email IN (:a, :b) ORDER BY email"),
                {"a": self.user_a_email, "b": self.user_b_email},
            ).fetchall()
            self.user_a_id = user_a_id[0]
            self.user_b_id = user_b_id[0]

            # Create tenant-scoped parent rows for both tenants and capture IDs.
            self.parents = {}
            for tenant_id, user_id in [(self.tenant_a, self.user_a_id), (self.tenant_b, self.user_b_id)]:
                conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
                goal_id = conn.execute(
                    text("""
                        INSERT INTO goals
                        (name, goal_type, status, target_amount, current_amount,
                         monthly_contribution, priority, tenant_id, created_at, updated_at)
                        VALUES
                        (:name, 'CUSTOM', 'ACTIVE', 1000, 0, 100, 1, :tenant_id, NOW(), NOW())
                        RETURNING id
                    """),
                    {"name": f"Goal {tenant_id} {self.run_id}", "tenant_id": tenant_id},
                ).scalar()
                loan_id = conn.execute(
                    text("""
                        INSERT INTO loans
                        (name, lender, loan_type, original_principal, current_balance,
                         interest_rate, start_date, repayment_strategy, extra_payment,
                         is_active, is_paid_off, tenant_id, created_at, updated_at)
                        VALUES
                        (:name, 'Bank', 'PERSONAL', 10000, 5000, 0.05, CURRENT_DATE,
                         'AVALANCHE', 0, true, false, :tenant_id, NOW(), NOW())
                        RETURNING id
                    """),
                    {"name": f"Loan {tenant_id} {self.run_id}", "tenant_id": tenant_id},
                ).scalar()
                session_id = conn.execute(
                    text("""
                        INSERT INTO ai_chat_sessions
                        (user_id, title, tenant_id, created_at, updated_at)
                        VALUES
                        (:user_id, :title, :tenant_id, NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "title": f"Chat {tenant_id} {self.run_id}",
                        "tenant_id": tenant_id,
                    },
                ).scalar()
                credit_profile_id = conn.execute(
                    text("""
                        INSERT INTO credit_profiles
                        (score, score_date, score_provider, tenant_id, created_at, updated_at)
                        VALUES
                        (700, CURRENT_DATE, 'test', :tenant_id, NOW(), NOW())
                        RETURNING id
                    """),
                    {"tenant_id": tenant_id},
                ).scalar()
                budget_id = conn.execute(
                    text("""
                        INSERT INTO budgets
                        (name, period, start_date, end_date, total_budgeted, total_actual,
                         is_active, tenant_id, created_at, updated_at)
                        VALUES
                        (:name, 'MONTHLY', CURRENT_DATE, CURRENT_DATE + 30, 1000, 0,
                         true, :tenant_id, NOW(), NOW())
                        RETURNING id
                    """),
                    {"name": f"Budget {tenant_id} {self.run_id}", "tenant_id": tenant_id},
                ).scalar()
                # Tenant subscription is scoped by organization_id directly.
                conn.execute(
                    text("""
                        INSERT INTO tenant_subscriptions
                        (organization_id, plan, status, started_at, amount, currency, created_at, updated_at)
                        VALUES
                        (:org_id, 'FREE', 'ACTIVE', NOW(), 0, 'USD', NOW(), NOW())
                    """),
                    {"org_id": tenant_id},
                )
                self.parents[tenant_id] = {
                    "goal_id": goal_id,
                    "loan_id": loan_id,
                    "session_id": session_id,
                    "credit_profile_id": credit_profile_id,
                    "budget_id": budget_id,
                }

            # Create child rows for both tenants.
            for tenant_id in (self.tenant_a, self.tenant_b):
                conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
                p = self.parents[tenant_id]
                conn.execute(
                    text("""
                        INSERT INTO goal_contributions
                        (goal_id, amount, date, source, created_at, updated_at)
                        VALUES (:goal_id, 100, CURRENT_DATE, 'manual', NOW(), NOW())
                    """),
                    {"goal_id": p["goal_id"]},
                )
                conn.execute(
                    text("""
                        INSERT INTO loan_payments
                        (loan_id, payment_date, total_payment, principal_paid,
                         interest_paid, remaining_balance, is_scheduled, created_at, updated_at)
                        VALUES (:loan_id, CURRENT_DATE, 100, 80, 20, 5000, false, NOW(), NOW())
                    """),
                    {"loan_id": p["loan_id"]},
                )
                conn.execute(
                    text("""
                        INSERT INTO ai_chat_messages
                        (session_id, role, content, created_at, updated_at)
                        VALUES (:session_id, 'user', 'Hello', NOW(), NOW())
                    """),
                    {"session_id": p["session_id"]},
                )
                conn.execute(
                    text("""
                        INSERT INTO credit_score_history
                        (credit_profile_id, score, date, created_at, updated_at)
                        VALUES (:credit_profile_id, 700, CURRENT_DATE, NOW(), NOW())
                    """),
                    {"credit_profile_id": p["credit_profile_id"]},
                )
                conn.execute(
                    text("""
                        INSERT INTO budget_categories
                        (budget_id, name, budgeted_amount, actual_amount, alert_threshold, created_at, updated_at)
                        VALUES (:budget_id, 'Groceries', 300, 0, 80, NOW(), NOW())
                    """),
                    {"budget_id": p["budget_id"]},
                )

            conn.commit()

        yield

        # Cleanup all synthetic rows.
        with engine.connect() as conn:
            for tenant_id in (self.tenant_a, self.tenant_b):
                conn.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
                # Delete children first.
                conn.execute(
                    text("DELETE FROM ai_chat_messages WHERE session_id IN (SELECT id FROM ai_chat_sessions WHERE tenant_id = :t)"),
                    {"t": tenant_id},
                )
                conn.execute(
                    text("DELETE FROM goal_contributions WHERE goal_id IN (SELECT id FROM goals WHERE tenant_id = :t)"),
                    {"t": tenant_id},
                )
                conn.execute(
                    text("DELETE FROM loan_payments WHERE loan_id IN (SELECT id FROM loans WHERE tenant_id = :t)"),
                    {"t": tenant_id},
                )
                conn.execute(
                    text("DELETE FROM credit_score_history WHERE credit_profile_id IN (SELECT id FROM credit_profiles WHERE tenant_id = :t)"),
                    {"t": tenant_id},
                )
                conn.execute(
                    text("DELETE FROM budget_categories WHERE budget_id IN (SELECT id FROM budgets WHERE tenant_id = :t)"),
                    {"t": tenant_id},
                )
                # Delete parents.
                conn.execute(text("DELETE FROM ai_chat_sessions WHERE tenant_id = :t"), {"t": tenant_id})
                conn.execute(text("DELETE FROM goals WHERE tenant_id = :t"), {"t": tenant_id})
                conn.execute(text("DELETE FROM loans WHERE tenant_id = :t"), {"t": tenant_id})
                conn.execute(text("DELETE FROM credit_profiles WHERE tenant_id = :t"), {"t": tenant_id})
                conn.execute(text("DELETE FROM budgets WHERE tenant_id = :t"), {"t": tenant_id})
                conn.execute(text("DELETE FROM tenant_subscriptions WHERE organization_id = :t"), {"t": tenant_id})

            # Delete users and organizations last.
            conn.execute(
                text("DELETE FROM users WHERE email IN (:a, :b)"),
                {"a": self.user_a_email, "b": self.user_b_email},
            )
            conn.execute(
                text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                {"a": self.tenant_a, "b": self.tenant_b},
            )
            conn.commit()

    def test_tenant_a_cannot_read_tenant_b_child_rows(self):
        """Tenant A context must not see Tenant B child rows."""
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_tenant_id = '{self.tenant_a}'"))
            for table, parent_col in [
                ("goal_contributions", "goal_id"),
                ("loan_payments", "loan_id"),
                ("ai_chat_messages", "session_id"),
                ("credit_score_history", "credit_profile_id"),
                ("budget_categories", "budget_id"),
            ]:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                assert result >= 1, f"Expected Tenant A to see its own {table} rows"

                # Ensure Tenant B rows are invisible.
                other_id = self.parents[self.tenant_b][parent_col]
                result = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE {parent_col} = :other_id"),
                    {"other_id": other_id},
                ).scalar()
                assert result == 0, f"Tenant A should not see {table} rows belonging to Tenant B"

            # tenant_subscriptions is scoped by organization_id directly.
            result = conn.execute(
                text("SELECT COUNT(*) FROM tenant_subscriptions WHERE organization_id = :other_id"),
                {"other_id": self.tenant_b},
            ).scalar()
            assert result == 0, "Tenant A should not see Tenant B subscriptions"

    def test_query_without_tenant_context_returns_zero_rows(self):
        """Direct query on a child table without tenant context must return zero rows."""
        with engine.connect() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = ''"))
            for table in [
                "goal_contributions",
                "loan_payments",
                "ai_chat_messages",
                "credit_score_history",
                "budget_categories",
                "tenant_subscriptions",
            ]:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                assert result == 0, f"Expected 0 rows for {table} without tenant context, got {result}"

    def test_tenant_context_through_parent_relationship_works(self):
        """Querying a child through its parent relationship respects the parent's tenant."""
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_tenant_id = '{self.tenant_a}'"))
            # Select children joined to their tenant-scoped parents.
            result = conn.execute(text("""
                SELECT m.id, s.tenant_id
                FROM ai_chat_messages m
                JOIN ai_chat_sessions s ON s.id = m.session_id
            """)).fetchall()
            assert len(result) >= 1
            for row in result:
                assert row.tenant_id == self.tenant_a

    def test_insert_cannot_attach_child_to_other_tenant_parent(self):
        """Inserting a child row referencing another tenant's parent must be blocked."""
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_tenant_id = '{self.tenant_a}'"))
            other_session_id = self.parents[self.tenant_b]["session_id"]
            with pytest.raises(Exception):
                conn.execute(
                    text("""
                        INSERT INTO ai_chat_messages
                        (session_id, role, content, created_at, updated_at)
                        VALUES (:session_id, 'user', 'cross-tenant', NOW(), NOW())
                    """),
                    {"session_id": other_session_id},
                )
                conn.commit()

    def test_update_cannot_move_child_to_other_tenant_parent(self):
        """Updating a child row to point to another tenant's parent must be blocked."""
        with engine.connect() as conn:
            conn.execute(text(f"SET LOCAL app.current_tenant_id = '{self.tenant_a}'"))
            own_message_id = conn.execute(
                text("SELECT id FROM ai_chat_messages LIMIT 1"),
            ).scalar()
            other_session_id = self.parents[self.tenant_b]["session_id"]
            with pytest.raises(Exception):
                conn.execute(
                    text("UPDATE ai_chat_messages SET session_id = :session_id WHERE id = :id"),
                    {"session_id": other_session_id, "id": own_message_id},
                )
                conn.commit()

    def test_rls_active_for_normal_app_database_user(self):
        """RLS must be active when using the same role the application uses."""
        with engine.connect() as conn:
            # Confirm the connected user is not a superuser and RLS is forced.
            current_user = conn.execute(text("SELECT current_user")).scalar()
            rls_forced = conn.execute(text("""
                SELECT relforcerowsecurity
                FROM pg_class
                WHERE relname = 'ai_chat_messages' AND relnamespace = 'public'::regnamespace
            """)).scalar()
            assert rls_forced is True, "ai_chat_messages must have FORCE ROW LEVEL SECURITY enabled"
            assert current_user != "postgres", "Tests should run as the application user, not superuser"
