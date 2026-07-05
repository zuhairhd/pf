"""add payment posting columns to bills and subscriptions

Revision ID: 89f59125ee5e
Revises: 334009b6ab5a
Create Date: 2026-07-03 19:18:08.298309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89f59125ee5e'
down_revision: Union[str, Sequence[str], None] = '334009b6ab5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment posting columns to bills and subscriptions."""
    # Bills
    op.add_column('bills', sa.Column('payment_account_id', sa.Integer(), nullable=True))
    op.add_column('bills', sa.Column('expense_account_id', sa.Integer(), nullable=True))
    op.add_column('bills', sa.Column('payment_journal_entry_id', sa.Integer(), nullable=True))
    op.create_index('ix_bills_payment_account_id', 'bills', ['payment_account_id'])
    op.create_index('ix_bills_expense_account_id', 'bills', ['expense_account_id'])
    op.create_index('ix_bills_payment_journal_entry_id', 'bills', ['payment_journal_entry_id'])
    op.create_foreign_key(
        'fk_bills_payment_account_id_accounts',
        'bills', 'accounts',
        ['payment_account_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_bills_expense_account_id_accounts',
        'bills', 'accounts',
        ['expense_account_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_bills_payment_journal_entry_id_journal_entries',
        'bills', 'journal_entries',
        ['payment_journal_entry_id'], ['id'],
        ondelete='SET NULL'
    )

    # Subscriptions
    op.add_column('subscriptions', sa.Column('payment_account_id', sa.Integer(), nullable=True))
    op.add_column('subscriptions', sa.Column('expense_account_id', sa.Integer(), nullable=True))
    op.add_column('subscriptions', sa.Column('payment_journal_entry_id', sa.Integer(), nullable=True))
    op.create_index('ix_subscriptions_payment_account_id', 'subscriptions', ['payment_account_id'])
    op.create_index('ix_subscriptions_expense_account_id', 'subscriptions', ['expense_account_id'])
    op.create_index('ix_subscriptions_payment_journal_entry_id', 'subscriptions', ['payment_journal_entry_id'])
    op.create_foreign_key(
        'fk_subscriptions_payment_account_id_accounts',
        'subscriptions', 'accounts',
        ['payment_account_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_subscriptions_expense_account_id_accounts',
        'subscriptions', 'accounts',
        ['expense_account_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_subscriptions_payment_journal_entry_id_journal_entries',
        'subscriptions', 'journal_entries',
        ['payment_journal_entry_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Remove payment posting columns."""
    # Subscriptions
    op.drop_constraint('fk_subscriptions_payment_journal_entry_id_journal_entries', 'subscriptions', type_='foreignkey')
    op.drop_constraint('fk_subscriptions_expense_account_id_accounts', 'subscriptions', type_='foreignkey')
    op.drop_constraint('fk_subscriptions_payment_account_id_accounts', 'subscriptions', type_='foreignkey')
    op.drop_index('ix_subscriptions_payment_journal_entry_id', 'subscriptions')
    op.drop_index('ix_subscriptions_expense_account_id', 'subscriptions')
    op.drop_index('ix_subscriptions_payment_account_id', 'subscriptions')
    op.drop_column('subscriptions', 'payment_journal_entry_id')
    op.drop_column('subscriptions', 'expense_account_id')
    op.drop_column('subscriptions', 'payment_account_id')

    # Bills
    op.drop_constraint('fk_bills_payment_journal_entry_id_journal_entries', 'bills', type_='foreignkey')
    op.drop_constraint('fk_bills_expense_account_id_accounts', 'bills', type_='foreignkey')
    op.drop_constraint('fk_bills_payment_account_id_accounts', 'bills', type_='foreignkey')
    op.drop_index('ix_bills_payment_journal_entry_id', 'bills')
    op.drop_index('ix_bills_expense_account_id', 'bills')
    op.drop_index('ix_bills_payment_account_id', 'bills')
    op.drop_column('bills', 'payment_journal_entry_id')
    op.drop_column('bills', 'expense_account_id')
    op.drop_column('bills', 'payment_account_id')
