"""add family finance foundation

Revision ID: 417e4cf19e63
Revises: a7c9d2e4f601
Create Date: 2026-07-08 11:40:06.887325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '417e4cf19e63'
down_revision: Union[str, Sequence[str], None] = 'a7c9d2e4f601'
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
    """Add family and family_members tables with tenant isolation."""
    # Family profile table (one per tenant).
    op.create_table(
        'families',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_families_id'), 'families', ['id'], unique=False)
    op.create_index(op.f('ix_families_tenant_id'), 'families', ['tenant_id'], unique=True)

    # Family members now belong to a family and a tenant.
    op.add_column('family_members', sa.Column('family_id', sa.Integer(), nullable=True))
    op.add_column('family_members', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.alter_column('family_members', 'user_id', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column(
        'family_members', 'role',
        existing_type=postgresql.ENUM('OWNER', 'ADMIN', 'EDITOR', 'VIEWER', name='userrole'),
        type_=sa.String(length=20),
        existing_nullable=False,
        postgresql_using="role::text",
    )

    # Backfill family_id and tenant_id from the owning user so existing rows
    # remain valid. The family itself is created for any rows that need one.
    op.execute(
        """
        INSERT INTO families (tenant_id, name, currency, created_at, updated_at)
        SELECT DISTINCT u.organization_id, 'Family', 'OMR', NOW(), NOW()
        FROM family_members fm
        JOIN users u ON u.id = fm.user_id
        WHERE fm.family_id IS NULL
        ON CONFLICT (tenant_id) DO NOTHING;

        UPDATE family_members fm
        SET tenant_id = u.organization_id,
            family_id = f.id
        FROM users u
        JOIN families f ON f.tenant_id = u.organization_id
        WHERE fm.user_id = u.id AND fm.family_id IS NULL;
        """
    )

    # Make family_id and tenant_id non-nullable now that they are populated.
    op.alter_column('family_members', 'family_id', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('family_members', 'tenant_id', existing_type=sa.INTEGER(), nullable=False)

    op.create_index(op.f('ix_family_members_email'), 'family_members', ['email'], unique=False)
    op.create_index(op.f('ix_family_members_family_id'), 'family_members', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_members_tenant_id'), 'family_members', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_family_members_user_id'), 'family_members', ['user_id'], unique=False)

    op.create_foreign_key(
        'fk_family_members_family_id_families',
        'family_members', 'families',
        ['family_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_family_members_tenant_id_organizations',
        'family_members', 'organizations',
        ['tenant_id'], ['id'],
        ondelete='CASCADE'
    )

    # RLS policies.
    op.execute(_rls_policy_sql('families'))
    op.execute(_rls_policy_sql('family_members'))


def downgrade() -> None:
    """Remove family finance tables and revert family_members changes."""
    op.execute("DROP POLICY IF EXISTS family_members_tenant_select ON family_members")
    op.execute("DROP POLICY IF EXISTS family_members_tenant_insert ON family_members")
    op.execute("DROP POLICY IF EXISTS family_members_tenant_update ON family_members")
    op.execute("DROP POLICY IF EXISTS family_members_tenant_delete ON family_members")
    op.execute("ALTER TABLE family_members NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE family_members DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS families_tenant_select ON families")
    op.execute("DROP POLICY IF EXISTS families_tenant_insert ON families")
    op.execute("DROP POLICY IF EXISTS families_tenant_update ON families")
    op.execute("DROP POLICY IF EXISTS families_tenant_delete ON families")
    op.execute("ALTER TABLE families NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE families DISABLE ROW LEVEL SECURITY")

    op.drop_constraint('fk_family_members_tenant_id_organizations', 'family_members', type_='foreignkey')
    op.drop_constraint('fk_family_members_family_id_families', 'family_members', type_='foreignkey')
    op.drop_index(op.f('ix_family_members_user_id'), table_name='family_members')
    op.drop_index(op.f('ix_family_members_tenant_id'), table_name='family_members')
    op.drop_index(op.f('ix_family_members_family_id'), table_name='family_members')
    op.drop_index(op.f('ix_family_members_email'), table_name='family_members')

    op.alter_column(
        'family_members', 'role',
        existing_type=sa.String(length=20),
        type_=postgresql.ENUM('OWNER', 'ADMIN', 'EDITOR', 'VIEWER', name='userrole'),
        existing_nullable=False,
        postgresql_using="role::userrole",
    )
    op.alter_column('family_members', 'user_id', existing_type=sa.INTEGER(), nullable=False)
    op.drop_column('family_members', 'tenant_id')
    op.drop_column('family_members', 'family_id')

    op.drop_index(op.f('ix_families_tenant_id'), table_name='families')
    op.drop_index(op.f('ix_families_id'), table_name='families')
    op.drop_table('families')
