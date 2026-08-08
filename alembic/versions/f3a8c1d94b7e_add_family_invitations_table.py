"""add family invitations table

Revision ID: f3a8c1d94b7e
Revises: a4c9e1f7b2d3
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d94b7e'
down_revision: Union[str, Sequence[str], None] = 'a4c9e1f7b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create family_invitations (AUTH-305).

    Intentionally NOT RLS-protected -- matching email_verifications and
    password_resets. Acceptance is driven by an unguessable bearer token
    before the caller has any tenant context, so an RLS policy requiring
    app.current_tenant_id to already be set would make the row unreadable
    to the very request that needs to look it up. Tenant isolation for the
    authenticated create/list/cancel operations is enforced at the service
    layer instead (see app/services/family_service.py), exactly like the
    users table already does for its own auth lookups. See app/core/rls.py
    GLOBAL_TABLES for the same documented rationale.
    """
    op.create_table(
        'family_invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('family_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('relationship_type', sa.String(length=50), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('invited_by_user_id', sa.Integer(), nullable=False),
        sa.Column('member_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['family_id'], ['families.id']),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['member_id'], ['family_members.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index(op.f('ix_family_invitations_id'), 'family_invitations', ['id'], unique=False)
    op.create_index(op.f('ix_family_invitations_tenant_id'), 'family_invitations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_family_invitations_family_id'), 'family_invitations', ['family_id'], unique=False)
    op.create_index(op.f('ix_family_invitations_email'), 'family_invitations', ['email'], unique=False)
    op.create_index(op.f('ix_family_invitations_token'), 'family_invitations', ['token'], unique=True)
    op.create_index(op.f('ix_family_invitations_status'), 'family_invitations', ['status'], unique=False)
    op.create_index(
        'ix_family_invitations_tenant_email_status',
        'family_invitations', ['tenant_id', 'email', 'status'], unique=False,
    )


def downgrade() -> None:
    """Drop family_invitations."""
    op.drop_index('ix_family_invitations_tenant_email_status', table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_status'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_token'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_email'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_family_id'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_tenant_id'), table_name='family_invitations')
    op.drop_index(op.f('ix_family_invitations_id'), table_name='family_invitations')
    op.drop_table('family_invitations')
