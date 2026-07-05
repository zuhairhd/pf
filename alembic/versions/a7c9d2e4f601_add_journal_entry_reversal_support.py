"""add journal entry reversal support

Revision ID: a7c9d2e4f601
Revises: 89f59125ee5e
Create Date: 2026-07-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c9d2e4f601'
down_revision: Union[str, Sequence[str], None] = '89f59125ee5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reversal metadata without altering posted accounting rows."""
    op.add_column('journal_entries', sa.Column('reversed_entry_id', sa.Integer(), nullable=True))
    op.add_column('journal_entries', sa.Column('reversal_entry_id', sa.Integer(), nullable=True))
    op.add_column('journal_entries', sa.Column('reversed_at', sa.DateTime(), nullable=True))
    op.add_column('journal_entries', sa.Column('reversal_reason', sa.Text(), nullable=True))
    op.create_index('ix_journal_entries_reversed_entry_id', 'journal_entries', ['reversed_entry_id'])
    op.create_index('ix_journal_entries_reversal_entry_id', 'journal_entries', ['reversal_entry_id'])
    op.create_foreign_key(
        'fk_journal_entries_reversed_entry_id_journal_entries',
        'journal_entries', 'journal_entries',
        ['reversed_entry_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_journal_entries_reversal_entry_id_journal_entries',
        'journal_entries', 'journal_entries',
        ['reversal_entry_id'], ['id'],
        ondelete='SET NULL',
    )

    op.add_column('bills', sa.Column('payment_reversal_journal_entry_id', sa.Integer(), nullable=True))
    op.create_index(
        'ix_bills_payment_reversal_journal_entry_id',
        'bills',
        ['payment_reversal_journal_entry_id'],
    )
    op.create_foreign_key(
        'fk_bills_payment_reversal_je_id',
        'bills', 'journal_entries',
        ['payment_reversal_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )

    op.add_column('subscriptions', sa.Column('payment_reversal_journal_entry_id', sa.Integer(), nullable=True))
    op.create_index(
        'ix_subscriptions_payment_reversal_journal_entry_id',
        'subscriptions',
        ['payment_reversal_journal_entry_id'],
    )
    op.create_foreign_key(
        'fk_subscriptions_payment_reversal_je_id',
        'subscriptions', 'journal_entries',
        ['payment_reversal_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove reversal metadata."""
    op.drop_constraint(
        'fk_subscriptions_payment_reversal_je_id',
        'subscriptions',
        type_='foreignkey',
    )
    op.drop_index('ix_subscriptions_payment_reversal_journal_entry_id', 'subscriptions')
    op.drop_column('subscriptions', 'payment_reversal_journal_entry_id')

    op.drop_constraint(
        'fk_bills_payment_reversal_je_id',
        'bills',
        type_='foreignkey',
    )
    op.drop_index('ix_bills_payment_reversal_journal_entry_id', 'bills')
    op.drop_column('bills', 'payment_reversal_journal_entry_id')

    op.drop_constraint(
        'fk_journal_entries_reversal_entry_id_journal_entries',
        'journal_entries',
        type_='foreignkey',
    )
    op.drop_constraint(
        'fk_journal_entries_reversed_entry_id_journal_entries',
        'journal_entries',
        type_='foreignkey',
    )
    op.drop_index('ix_journal_entries_reversal_entry_id', 'journal_entries')
    op.drop_index('ix_journal_entries_reversed_entry_id', 'journal_entries')
    op.drop_column('journal_entries', 'reversal_reason')
    op.drop_column('journal_entries', 'reversed_at')
    op.drop_column('journal_entries', 'reversal_entry_id')
    op.drop_column('journal_entries', 'reversed_entry_id')
