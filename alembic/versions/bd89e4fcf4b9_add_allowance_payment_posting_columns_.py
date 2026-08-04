"""add allowance payment posting columns to family chore completions

Revision ID: bd89e4fcf4b9
Revises: 356391296d35
Create Date: 2026-08-04 05:00:30.714299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd89e4fcf4b9'
down_revision: Union[str, Sequence[str], None] = '356391296d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add allowance payment posting columns to family_chore_completions.

    Nullable/defaulted columns only; existing rows are preserved as
    unpaid. No table is dropped or recreated and RLS/FORCE RLS on
    family_chore_completions is untouched by adding columns.
    """
    op.add_column(
        'family_chore_completions',
        sa.Column('payment_status', sa.String(length=20), nullable=False, server_default='unpaid'),
    )
    op.add_column('family_chore_completions', sa.Column('payment_account_id', sa.Integer(), nullable=True))
    op.add_column('family_chore_completions', sa.Column('expense_account_id', sa.Integer(), nullable=True))
    op.add_column('family_chore_completions', sa.Column('payment_journal_entry_id', sa.Integer(), nullable=True))
    op.add_column(
        'family_chore_completions',
        sa.Column('payment_reversal_journal_entry_id', sa.Integer(), nullable=True),
    )
    op.add_column('family_chore_completions', sa.Column('paid_at', sa.DateTime(), nullable=True))
    op.add_column('family_chore_completions', sa.Column('paid_by_user_id', sa.Integer(), nullable=True))

    op.create_index(
        op.f('ix_family_chore_completions_payment_status'),
        'family_chore_completions', ['payment_status'], unique=False,
    )
    op.create_index(
        op.f('ix_family_chore_completions_payment_account_id'),
        'family_chore_completions', ['payment_account_id'], unique=False,
    )
    op.create_index(
        op.f('ix_family_chore_completions_expense_account_id'),
        'family_chore_completions', ['expense_account_id'], unique=False,
    )
    op.create_index(
        op.f('ix_family_chore_completions_payment_journal_entry_id'),
        'family_chore_completions', ['payment_journal_entry_id'], unique=False,
    )
    op.create_index(
        op.f('ix_family_chore_completions_payment_reversal_journal_entry_id'),
        'family_chore_completions', ['payment_reversal_journal_entry_id'], unique=False,
    )
    op.create_index(
        op.f('ix_family_chore_completions_paid_by_user_id'),
        'family_chore_completions', ['paid_by_user_id'], unique=False,
    )
    op.create_index(
        'ix_family_chore_completions_tenant_payment_status',
        'family_chore_completions', ['tenant_id', 'payment_status'], unique=False,
    )

    op.create_foreign_key(
        'fk_family_chore_completions_payment_account_id_accounts',
        'family_chore_completions', 'accounts',
        ['payment_account_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_family_chore_completions_expense_account_id_accounts',
        'family_chore_completions', 'accounts',
        ['expense_account_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_family_chore_completions_payment_je_id_journal_entries',
        'family_chore_completions', 'journal_entries',
        ['payment_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_family_chore_completions_payment_reversal_je_id_je',
        'family_chore_completions', 'journal_entries',
        ['payment_reversal_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_family_chore_completions_paid_by_user_id_users',
        'family_chore_completions', 'users',
        ['paid_by_user_id'], ['id'],
        ondelete='SET NULL',
    )

    # Remove the server default so future inserts rely on the application/model default.
    op.alter_column('family_chore_completions', 'payment_status', server_default=None)


def downgrade() -> None:
    """Remove allowance payment posting columns from family_chore_completions."""
    op.drop_constraint(
        'fk_family_chore_completions_paid_by_user_id_users',
        'family_chore_completions', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_family_chore_completions_payment_reversal_je_id_je',
        'family_chore_completions', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_family_chore_completions_payment_je_id_journal_entries',
        'family_chore_completions', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_family_chore_completions_expense_account_id_accounts',
        'family_chore_completions', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_family_chore_completions_payment_account_id_accounts',
        'family_chore_completions', type_='foreignkey',
    )

    op.drop_index('ix_family_chore_completions_tenant_payment_status', table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_paid_by_user_id'), table_name='family_chore_completions')
    op.drop_index(
        op.f('ix_family_chore_completions_payment_reversal_journal_entry_id'),
        table_name='family_chore_completions',
    )
    op.drop_index(
        op.f('ix_family_chore_completions_payment_journal_entry_id'),
        table_name='family_chore_completions',
    )
    op.drop_index(op.f('ix_family_chore_completions_expense_account_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_payment_account_id'), table_name='family_chore_completions')
    op.drop_index(op.f('ix_family_chore_completions_payment_status'), table_name='family_chore_completions')

    op.drop_column('family_chore_completions', 'paid_by_user_id')
    op.drop_column('family_chore_completions', 'paid_at')
    op.drop_column('family_chore_completions', 'payment_reversal_journal_entry_id')
    op.drop_column('family_chore_completions', 'payment_journal_entry_id')
    op.drop_column('family_chore_completions', 'expense_account_id')
    op.drop_column('family_chore_completions', 'payment_account_id')
    op.drop_column('family_chore_completions', 'payment_status')
