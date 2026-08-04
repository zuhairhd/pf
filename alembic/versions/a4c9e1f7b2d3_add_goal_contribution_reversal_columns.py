"""add goal contribution reversal columns

Revision ID: a4c9e1f7b2d3
Revises: bd89e4fcf4b9
Create Date: 2026-08-05 03:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c9e1f7b2d3'
down_revision: Union[str, Sequence[str], None] = 'bd89e4fcf4b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add goal contribution reversal columns to goal_contributions.

    Nullable columns only; existing rows are preserved and default to
    unreversed. No table is dropped or recreated and RLS/FORCE RLS on
    goal_contributions is untouched by adding columns.
    """
    op.add_column('goal_contributions', sa.Column('reversal_journal_entry_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('reversed_at', sa.DateTime(), nullable=True))
    op.add_column('goal_contributions', sa.Column('reversed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('reversal_reason', sa.Text(), nullable=True))

    op.create_index(
        op.f('ix_goal_contributions_reversal_journal_entry_id'),
        'goal_contributions', ['reversal_journal_entry_id'], unique=False,
    )
    op.create_index(
        op.f('ix_goal_contributions_reversed_by_user_id'),
        'goal_contributions', ['reversed_by_user_id'], unique=False,
    )

    op.create_foreign_key(
        'fk_goal_contributions_reversal_je_id_journal_entries',
        'goal_contributions', 'journal_entries',
        ['reversal_journal_entry_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_goal_contributions_reversed_by_user_id_users',
        'goal_contributions', 'users',
        ['reversed_by_user_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove goal contribution reversal columns from goal_contributions."""
    op.drop_constraint(
        'fk_goal_contributions_reversed_by_user_id_users',
        'goal_contributions', type_='foreignkey',
    )
    op.drop_constraint(
        'fk_goal_contributions_reversal_je_id_journal_entries',
        'goal_contributions', type_='foreignkey',
    )

    op.drop_index(op.f('ix_goal_contributions_reversed_by_user_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_reversal_journal_entry_id'), table_name='goal_contributions')

    op.drop_column('goal_contributions', 'reversal_reason')
    op.drop_column('goal_contributions', 'reversed_by_user_id')
    op.drop_column('goal_contributions', 'reversed_at')
    op.drop_column('goal_contributions', 'reversal_journal_entry_id')
