"""Add admin access sessions table

Revision ID: 542823443f9e
Revises: df41f5ea2f46
Create Date: 2026-07-02 09:41:00.349514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '542823443f9e'
down_revision: Union[str, Sequence[str], None] = 'df41f5ea2f46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the global audit table for super-admin support sessions."""

    op.create_table(
        'admin_access_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('admin_user_id', sa.Integer(), nullable=False),
        sa.Column('target_organization_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('access_started_at', sa.DateTime(), nullable=False),
        sa.Column('access_expires_at', sa.DateTime(), nullable=False),
        sa.Column('access_ended_at', sa.DateTime(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name='ck_admin_access_sessions_status'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['target_organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Indexes for audit lookups.
    op.create_index(
        op.f('ix_admin_access_sessions_admin_user_id'),
        'admin_access_sessions',
        ['admin_user_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_admin_access_sessions_target_organization_id'),
        'admin_access_sessions',
        ['target_organization_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_admin_access_sessions_status'),
        'admin_access_sessions',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_admin_access_sessions_access_expires_at'),
        'admin_access_sessions',
        ['access_expires_at'],
        unique=False,
    )


def downgrade() -> None:
    """Drop the admin access sessions table and its enum."""

    op.drop_index(
        op.f('ix_admin_access_sessions_access_expires_at'),
        table_name='admin_access_sessions',
    )
    op.drop_index(
        op.f('ix_admin_access_sessions_status'),
        table_name='admin_access_sessions',
    )
    op.drop_index(
        op.f('ix_admin_access_sessions_target_organization_id'),
        table_name='admin_access_sessions',
    )
    op.drop_index(
        op.f('ix_admin_access_sessions_admin_user_id'),
        table_name='admin_access_sessions',
    )
    op.drop_table('admin_access_sessions')


