"""add bill payment tracking and subscription status

Revision ID: c7ec07582862
Revises: 9ee380da96d5
Create Date: 2026-07-03 15:44:17.502329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7ec07582862'
down_revision: Union[str, Sequence[str], None] = '9ee380da96d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add payment tracking to bills.
    op.add_column(
        'bills',
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.add_column(
        'bills',
        sa.Column('paid_at', sa.DateTime(), nullable=True)
    )

    # Add status string to subscriptions (active / paused / cancelled).
    # Using a plain string avoids conflicting with the existing PostgreSQL
    # "subscriptionstatus" enum used by tenant subscriptions.
    op.add_column(
        'subscriptions',
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'")
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('subscriptions', 'status')
    op.drop_column('bills', 'paid_at')
    op.drop_column('bills', 'is_paid')
