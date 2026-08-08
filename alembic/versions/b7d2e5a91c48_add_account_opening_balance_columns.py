"""add account opening balance columns

Revision ID: b7d2e5a91c48
Revises: f3a8c1d94b7e
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e5a91c48'
down_revision: Union[str, Sequence[str], None] = 'f3a8c1d94b7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add opening balance columns to accounts (ACC-502).

    Nullable columns only; existing rows are preserved and default to no
    configured opening balance (NULL, distinct from a configured zero). No
    table is dropped or recreated and RLS/FORCE RLS on accounts is untouched
    by adding columns.
    """
    op.add_column('accounts', sa.Column('opening_balance', sa.Numeric(precision=15, scale=3), nullable=True))
    op.add_column('accounts', sa.Column('opening_balance_date', sa.Date(), nullable=True))
    op.add_column('accounts', sa.Column('opening_balance_journal_entry_id', sa.Integer(), nullable=True))

    op.create_index(
        op.f('ix_accounts_opening_balance_journal_entry_id'),
        'accounts', ['opening_balance_journal_entry_id'], unique=False,
    )
    op.create_foreign_key(
        'fk_accounts_opening_balance_je_id_journal_entries',
        'accounts', 'journal_entries',
        ['opening_balance_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove opening balance columns from accounts."""
    op.drop_constraint(
        'fk_accounts_opening_balance_je_id_journal_entries',
        'accounts', type_='foreignkey',
    )
    op.drop_index(op.f('ix_accounts_opening_balance_journal_entry_id'), table_name='accounts')

    op.drop_column('accounts', 'opening_balance_journal_entry_id')
    op.drop_column('accounts', 'opening_balance_date')
    op.drop_column('accounts', 'opening_balance')
