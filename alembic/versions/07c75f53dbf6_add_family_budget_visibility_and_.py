"""add family budget visibility and ownership columns

Revision ID: 07c75f53dbf6
Revises: 360b89eed134
Create Date: 2026-08-03 06:08:24.345115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07c75f53dbf6'
down_revision: Union[str, Sequence[str], None] = '360b89eed134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add family ownership/visibility/status/currency to budgets (FAM-1303).

    RLS is unaffected: `budgets` already has direct tenant-scoped RLS
    policies (from the initial RLS migration) and `budget_categories`
    already has join-based child-table RLS through `budgets.tenant_id`
    (from the child-table RLS coverage migration). Adding columns to an
    already-covered table requires no policy changes.
    """
    op.add_column(
        'budgets',
        sa.Column('visibility', sa.String(length=20), nullable=False, server_default='private'),
    )
    op.add_column(
        'budgets',
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
    )
    op.add_column(
        'budgets',
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='OMR'),
    )
    op.add_column('budgets', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('budgets', sa.Column('family_id', sa.Integer(), nullable=True))
    op.add_column('budgets', sa.Column('created_by_user_id', sa.Integer(), nullable=True))

    op.create_index(op.f('ix_budgets_visibility'), 'budgets', ['visibility'], unique=False)
    op.create_index(op.f('ix_budgets_status'), 'budgets', ['status'], unique=False)
    op.create_index(op.f('ix_budgets_owner_user_id'), 'budgets', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_budgets_family_id'), 'budgets', ['family_id'], unique=False)
    op.create_index(op.f('ix_budgets_created_by_user_id'), 'budgets', ['created_by_user_id'], unique=False)
    op.create_index(
        'ix_budgets_tenant_period', 'budgets', ['tenant_id', 'start_date', 'end_date'], unique=False
    )

    op.create_foreign_key(
        'fk_budgets_family_id_families',
        'budgets', 'families',
        ['family_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_budgets_owner_user_id_users',
        'budgets', 'users',
        ['owner_user_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_budgets_created_by_user_id_users',
        'budgets', 'users',
        ['created_by_user_id'], ['id'],
    )

    # Remove server defaults so future inserts rely on the application/model default.
    op.alter_column('budgets', 'visibility', server_default=None)
    op.alter_column('budgets', 'status', server_default=None)
    op.alter_column('budgets', 'currency', server_default=None)


def downgrade() -> None:
    """Remove family ownership/visibility/status/currency from budgets."""
    op.drop_constraint('fk_budgets_created_by_user_id_users', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budgets_owner_user_id_users', 'budgets', type_='foreignkey')
    op.drop_constraint('fk_budgets_family_id_families', 'budgets', type_='foreignkey')

    op.drop_index('ix_budgets_tenant_period', table_name='budgets')
    op.drop_index(op.f('ix_budgets_created_by_user_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_family_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_owner_user_id'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_status'), table_name='budgets')
    op.drop_index(op.f('ix_budgets_visibility'), table_name='budgets')

    op.drop_column('budgets', 'created_by_user_id')
    op.drop_column('budgets', 'family_id')
    op.drop_column('budgets', 'owner_user_id')
    op.drop_column('budgets', 'currency')
    op.drop_column('budgets', 'status')
    op.drop_column('budgets', 'visibility')
