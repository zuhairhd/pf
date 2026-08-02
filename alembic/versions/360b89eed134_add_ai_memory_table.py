"""add ai memory table

Revision ID: 360b89eed134
Revises: 5e8169dd3017
Create Date: 2026-08-01 09:23:49.358469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '360b89eed134'
down_revision: Union[str, Sequence[str], None] = '5e8169dd3017'
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
    """Upgrade schema."""
    op.create_table(
        'ai_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'memory_type',
            sa.Enum(
                'PREFERENCE', 'GOAL_CONTEXT', 'RISK_PROFILE',
                'BEHAVIOR_PATTERN', 'DISMISSED_ADVICE', 'CUSTOM',
                name='aimemorytype',
            ),
            nullable=False,
        ),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('summary', sa.String(length=255), nullable=True),
        sa.Column(
            'source',
            sa.Enum(
                'EXPLICIT_USER_STATEMENT', 'CHAT_INFERRED', 'SYSTEM_GENERATED',
                name='aimemorysource',
            ),
            nullable=False,
        ),
        sa.Column('confidence_score', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_sensitive', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_memories_id'), 'ai_memories', ['id'], unique=False)
    op.create_index(op.f('ix_ai_memories_tenant_id'), 'ai_memories', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_ai_memories_user_id'), 'ai_memories', ['user_id'], unique=False)
    op.create_index(op.f('ix_ai_memories_memory_type'), 'ai_memories', ['memory_type'], unique=False)
    op.create_index(op.f('ix_ai_memories_key'), 'ai_memories', ['key'], unique=False)
    op.create_index(op.f('ix_ai_memories_is_active'), 'ai_memories', ['is_active'], unique=False)

    op.execute(_rls_policy_sql('ai_memories'))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS ai_memories_tenant_select ON ai_memories")
    op.execute("DROP POLICY IF EXISTS ai_memories_tenant_insert ON ai_memories")
    op.execute("DROP POLICY IF EXISTS ai_memories_tenant_update ON ai_memories")
    op.execute("DROP POLICY IF EXISTS ai_memories_tenant_delete ON ai_memories")
    op.execute("ALTER TABLE ai_memories NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_memories DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f('ix_ai_memories_is_active'), table_name='ai_memories')
    op.drop_index(op.f('ix_ai_memories_key'), table_name='ai_memories')
    op.drop_index(op.f('ix_ai_memories_memory_type'), table_name='ai_memories')
    op.drop_index(op.f('ix_ai_memories_user_id'), table_name='ai_memories')
    op.drop_index(op.f('ix_ai_memories_tenant_id'), table_name='ai_memories')
    op.drop_index(op.f('ix_ai_memories_id'), table_name='ai_memories')
    op.drop_table('ai_memories')
