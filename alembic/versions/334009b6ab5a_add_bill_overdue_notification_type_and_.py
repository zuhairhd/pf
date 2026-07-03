"""add_bill_overdue_notification_type_and_verify_rls

Revision ID: 334009b6ab5a
Revises: 196cef681c37
Create Date: 2026-07-03 16:29:19.194055

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '334009b6ab5a'
down_revision: Union[str, Sequence[str], None] = '196cef681c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add BILL_OVERDUE to the notificationtype enum and keep RLS enabled."""
    # PostgreSQL does not support removing enum values, so the downgrade is a no-op.
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'BILL_OVERDUE'")

    # Ensure the notifications table remains protected by RLS.
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema.

    Enum values cannot be removed safely in PostgreSQL, so this is intentionally
    empty for this migration.
    """
    pass
