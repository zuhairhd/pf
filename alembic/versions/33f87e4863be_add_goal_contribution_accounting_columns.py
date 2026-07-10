"""add goal contribution accounting columns

Revision ID: 33f87e4863be
Revises: 951f42580bfd
Create Date: 2026-07-10 07:15:18.634309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33f87e4863be'
down_revision: Union[str, Sequence[str], None] = '951f42580bfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add accounting posting columns to goal_contributions."""
    # Add nullable account/journal linkage columns.
    op.add_column('goal_contributions', sa.Column('source_account_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('destination_account_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('journal_entry_id', sa.Integer(), nullable=True))
    op.add_column(
        'goal_contributions',
        sa.Column('posting_status', sa.String(length=20), nullable=False, server_default='progress_only'),
    )

    # Indexes for the new foreign keys.
    op.create_index(op.f('ix_goal_contributions_source_account_id'), 'goal_contributions', ['source_account_id'], unique=False)
    op.create_index(op.f('ix_goal_contributions_destination_account_id'), 'goal_contributions', ['destination_account_id'], unique=False)
    op.create_index(op.f('ix_goal_contributions_journal_entry_id'), 'goal_contributions', ['journal_entry_id'], unique=False)

    # Foreign keys.
    op.create_foreign_key(
        'fk_goal_contributions_source_account_id_accounts',
        'goal_contributions', 'accounts',
        ['source_account_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_goal_contributions_destination_account_id_accounts',
        'goal_contributions', 'accounts',
        ['destination_account_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_goal_contributions_journal_entry_id_journal_entries',
        'goal_contributions', 'journal_entries',
        ['journal_entry_id'], ['id'],
    )

    # Remove server default so future inserts rely on the application/model default.
    op.alter_column('goal_contributions', 'posting_status', server_default=None)


def downgrade() -> None:
    """Remove accounting posting columns from goal_contributions."""
    op.drop_constraint('fk_goal_contributions_journal_entry_id_journal_entries', 'goal_contributions', type_='foreignkey')
    op.drop_constraint('fk_goal_contributions_destination_account_id_accounts', 'goal_contributions', type_='foreignkey')
    op.drop_constraint('fk_goal_contributions_source_account_id_accounts', 'goal_contributions', type_='foreignkey')

    op.drop_index(op.f('ix_goal_contributions_journal_entry_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_destination_account_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_source_account_id'), table_name='goal_contributions')

    op.drop_column('goal_contributions', 'posting_status')
    op.drop_column('goal_contributions', 'journal_entry_id')
    op.drop_column('goal_contributions', 'destination_account_id')
    op.drop_column('goal_contributions', 'source_account_id')
