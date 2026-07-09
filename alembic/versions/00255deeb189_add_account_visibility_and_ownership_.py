"""add account visibility and ownership columns

Revision ID: 00255deeb189
Revises: 417e4cf19e63
Create Date: 2026-07-09 03:33:03.817730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00255deeb189'
down_revision: Union[str, Sequence[str], None] = '417e4cf19e63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add visibility/ownership columns to accounts."""
    op.add_column(
        'accounts',
        sa.Column('visibility', sa.String(length=20), nullable=False, server_default='private'),
    )
    op.add_column('accounts', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('accounts', sa.Column('family_id', sa.Integer(), nullable=True))

    op.create_index(op.f('ix_accounts_family_id'), 'accounts', ['family_id'], unique=False)
    op.create_index(op.f('ix_accounts_owner_user_id'), 'accounts', ['owner_user_id'], unique=False)
    op.create_index('ix_accounts_tenant_owner', 'accounts', ['tenant_id', 'owner_user_id'], unique=False)
    op.create_index('ix_accounts_tenant_visibility', 'accounts', ['tenant_id', 'visibility'], unique=False)
    op.create_index(op.f('ix_accounts_visibility'), 'accounts', ['visibility'], unique=False)

    op.create_foreign_key(
        'fk_accounts_owner_user_id_users',
        'accounts', 'users',
        ['owner_user_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_accounts_family_id_families',
        'accounts', 'families',
        ['family_id'], ['id'],
    )

    # Remove the server default so future inserts rely on the application/model default.
    op.alter_column('accounts', 'visibility', server_default=None)


def downgrade() -> None:
    """Remove visibility/ownership columns from accounts."""
    op.drop_constraint('fk_accounts_owner_user_id_users', 'accounts', type_='foreignkey')
    op.drop_constraint('fk_accounts_family_id_families', 'accounts', type_='foreignkey')

    op.drop_index(op.f('ix_accounts_visibility'), table_name='accounts')
    op.drop_index('ix_accounts_tenant_visibility', table_name='accounts')
    op.drop_index('ix_accounts_tenant_owner', table_name='accounts')
    op.drop_index(op.f('ix_accounts_owner_user_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_family_id'), table_name='accounts')

    op.drop_column('accounts', 'family_id')
    op.drop_column('accounts', 'owner_user_id')
    op.drop_column('accounts', 'visibility')
