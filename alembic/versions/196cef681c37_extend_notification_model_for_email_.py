"""extend notification model for email reminders

Revision ID: 196cef681c37
Revises: c7ec07582862
Create Date: 2026-07-03 16:15:37.296200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '196cef681c37'
down_revision: Union[str, Sequence[str], None] = 'c7ec07582862'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


notification_channel_enum = sa.Enum('IN_APP', 'EMAIL', 'PUSH', 'SMS', name='notificationchannel')
notification_status_enum = sa.Enum('PENDING', 'SENT', 'FAILED', 'SKIPPED', 'READ', name='notificationstatus')


def upgrade() -> None:
    """Extend notifications with email/reminder tracking fields."""
    notification_channel_enum.create(op.get_bind(), checkfirst=True)
    notification_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'notifications',
        sa.Column(
            'channel',
            notification_channel_enum,
            nullable=False,
            server_default=sa.text("'IN_APP'")
        )
    )
    op.add_column(
        'notifications',
        sa.Column(
            'status',
            notification_status_enum,
            nullable=False,
            server_default=sa.text("'PENDING'")
        )
    )
    op.add_column('notifications', sa.Column('scheduled_for', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('sent_at', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('notifications', sa.Column('related_entity_type', sa.String(length=50), nullable=True))
    op.add_column('notifications', sa.Column('related_entity_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'related_entity_id')
    op.drop_column('notifications', 'related_entity_type')
    op.drop_column('notifications', 'error_message')
    op.drop_column('notifications', 'sent_at')
    op.drop_column('notifications', 'scheduled_for')
    op.drop_column('notifications', 'status')
    op.drop_column('notifications', 'channel')

    notification_status_enum.drop(op.get_bind(), checkfirst=True)
    notification_channel_enum.drop(op.get_bind(), checkfirst=True)
