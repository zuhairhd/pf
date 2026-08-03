"""add family chore and completion tables

Revision ID: 356391296d35
Revises: 07c75f53dbf6
Create Date: 2026-08-03 19:19:17.918038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '356391296d35'
down_revision: Union[str, Sequence[str], None] = '07c75f53dbf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_policy_sql(table: str) -> str:
    """Return RLS policy definitions for a tenant-scoped table."""
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

    CREATE POLICY {table}_tenant_select ON {table}
        FOR SELECT
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_insert ON {table}
        FOR INSERT
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_update ON {table}
        FOR UPDATE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_delete ON {table}
        FOR DELETE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);
    """


def upgrade() -> None:
    """Create family_chores and family_chore_completions with RLS + FORCE RLS.

    Brand-new tables; no existing data is touched or migrated.
    """
    op.create_table(
        'family_chores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assigned_to_member_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('allowance_amount', sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('frequency', sa.String(length=20), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.ForeignKeyConstraint(['assigned_to_member_id'], ['family_members.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_family_chores_id'), 'family_chores', ['id'], unique=False)
    op.create_index(op.f('ix_family_chores_tenant_id'), 'family_chores', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_family_chores_family_id'), 'family_chores', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_chores_assigned_to_member_id'), 'family_chores', ['assigned_to_member_id'], unique=False)
    op.create_index(op.f('ix_family_chores_status'), 'family_chores', ['status'], unique=False)
    op.create_index('ix_family_chores_tenant_status', 'family_chores', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_family_chores_tenant_assigned', 'family_chores', ['tenant_id', 'assigned_to_member_id'], unique=False)
    op.create_index('ix_family_chores_tenant_due_date', 'family_chores', ['tenant_id', 'due_date'], unique=False)

    op.create_table(
        'family_chore_completions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chore_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('completed_by_member_id', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False),
        sa.Column('submitted_notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('approved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('earned_amount', sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['chore_id'], ['family_chores.id']),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.ForeignKeyConstraint(['completed_by_member_id'], ['family_members.id']),
        sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_family_chore_completions_id'), 'family_chore_completions', ['id'], unique=False)
    op.create_index(op.f('ix_family_chore_completions_tenant_id'), 'family_chore_completions', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_family_chore_completions_chore_id'), 'family_chore_completions', ['chore_id'], unique=False)
    op.create_index(op.f('ix_family_chore_completions_family_id'), 'family_chore_completions', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_chore_completions_completed_by_member_id'), 'family_chore_completions', ['completed_by_member_id'], unique=False)
    op.create_index(op.f('ix_family_chore_completions_status'), 'family_chore_completions', ['status'], unique=False)
    op.create_index('ix_family_chore_completions_tenant_status', 'family_chore_completions', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_family_chore_completions_tenant_member', 'family_chore_completions', ['tenant_id', 'completed_by_member_id'], unique=False)

    op.execute(_rls_policy_sql('family_chores'))
    op.execute(_rls_policy_sql('family_chore_completions'))


def downgrade() -> None:
    """Drop RLS policies and the family_chores / family_chore_completions tables."""
    op.execute("DROP POLICY IF EXISTS family_chore_completions_tenant_select ON family_chore_completions")
    op.execute("DROP POLICY IF EXISTS family_chore_completions_tenant_insert ON family_chore_completions")
    op.execute("DROP POLICY IF EXISTS family_chore_completions_tenant_update ON family_chore_completions")
    op.execute("DROP POLICY IF EXISTS family_chore_completions_tenant_delete ON family_chore_completions")
    op.execute("ALTER TABLE family_chore_completions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE family_chore_completions DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS family_chores_tenant_select ON family_chores")
    op.execute("DROP POLICY IF EXISTS family_chores_tenant_insert ON family_chores")
    op.execute("DROP POLICY IF EXISTS family_chores_tenant_update ON family_chores")
    op.execute("DROP POLICY IF EXISTS family_chores_tenant_delete ON family_chores")
    op.execute("ALTER TABLE family_chores NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE family_chores DISABLE ROW LEVEL SECURITY")

    op.drop_index('ix_family_chore_completions_tenant_member', table_name='family_chore_completions')
    op.drop_index('ix_family_chore_completions_tenant_status', table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_status'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_completed_by_member_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_family_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_chore_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_tenant_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_id'), table_name='family_chore_completions')
    op.drop_table('family_chore_completions')

    op.drop_index('ix_family_chores_tenant_due_date', table_name='family_chores')
    op.drop_index('ix_family_chores_tenant_assigned', table_name='family_chores')
    op.drop_index('ix_family_chores_tenant_status', table_name='family_chores')
    op.drop_index(op.f('ix_family_chores_status'), table_name='family_chores')
    op.drop_index(op.f('ix_family_chores_assigned_to_member_id'), table_name='family_chores')
    op.drop_index(op.f('ix_family_chores_family_id'), table_name='family_chores')
    op.drop_index(op.f('ix_family_chores_tenant_id'), table_name='family_chores')
    op.drop_index(op.f('ix_family_chores_id'), table_name='family_chores')
    op.drop_table('family_chores')
