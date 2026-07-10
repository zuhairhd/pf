"""add family goal visibility and contribution ownership

Revision ID: 951f42580bfd
Revises: 00255deeb189
Create Date: 2026-07-10 05:30:25.127363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '951f42580bfd'
down_revision: Union[str, Sequence[str], None] = '00255deeb189'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add family ownership and visibility to goals and tenant ownership to contributions."""
    # Family visibility/ownership columns on goals.
    op.add_column(
        'goals',
        sa.Column('visibility', sa.String(length=20), nullable=False, server_default='private'),
    )
    op.add_column('goals', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('goals', sa.Column('family_id', sa.Integer(), nullable=True))

    op.create_index(op.f('ix_goals_family_id'), 'goals', ['family_id'], unique=False)
    op.create_index(op.f('ix_goals_owner_user_id'), 'goals', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_goals_visibility'), 'goals', ['visibility'], unique=False)

    op.create_foreign_key(
        'fk_goals_family_id_families',
        'goals', 'families',
        ['family_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_goals_owner_user_id_users',
        'goals', 'users',
        ['owner_user_id'], ['id'],
    )

    # Remove the server default so future inserts rely on the application/model default.
    op.alter_column('goals', 'visibility', server_default=None)

    # Tenant and contributor ownership on goal_contributions.
    op.add_column('goal_contributions', sa.Column('tenant_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('contributed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('goal_contributions', sa.Column('account_id', sa.Integer(), nullable=True))

    op.create_index(op.f('ix_goal_contributions_tenant_id'), 'goal_contributions', ['tenant_id'], unique=False)
    op.create_index(
        op.f('ix_goal_contributions_contributed_by_user_id'),
        'goal_contributions',
        ['contributed_by_user_id'],
        unique=False,
    )
    op.create_index(op.f('ix_goal_contributions_account_id'), 'goal_contributions', ['account_id'], unique=False)

    op.create_foreign_key(
        'fk_goal_contributions_contributed_by_user_id_users',
        'goal_contributions', 'users',
        ['contributed_by_user_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_goal_contributions_account_id_accounts',
        'goal_contributions', 'accounts',
        ['account_id'], ['id'],
    )

    # Backfill tenant_id from parent goals so we can make it non-nullable.
    op.execute(
        """
        UPDATE goal_contributions
        SET tenant_id = goals.tenant_id
        FROM goals
        WHERE goal_contributions.goal_id = goals.id
        """
    )
    op.alter_column('goal_contributions', 'tenant_id', nullable=False)


def downgrade() -> None:
    """Remove family ownership/visibility from goals and tenant ownership from contributions."""
    op.drop_constraint('fk_goal_contributions_account_id_accounts', 'goal_contributions', type_='foreignkey')
    op.drop_constraint('fk_goal_contributions_contributed_by_user_id_users', 'goal_contributions', type_='foreignkey')

    op.drop_index(op.f('ix_goal_contributions_account_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_contributed_by_user_id'), table_name='goal_contributions')
    op.drop_index(op.f('ix_goal_contributions_tenant_id'), table_name='goal_contributions')

    op.drop_column('goal_contributions', 'account_id')
    op.drop_column('goal_contributions', 'contributed_by_user_id')
    op.drop_column('goal_contributions', 'tenant_id')

    op.drop_constraint('fk_goals_owner_user_id_users', 'goals', type_='foreignkey')
    op.drop_constraint('fk_goals_family_id_families', 'goals', type_='foreignkey')

    op.drop_index(op.f('ix_goals_visibility'), table_name='goals')
    op.drop_index(op.f('ix_goals_owner_user_id'), table_name='goals')
    op.drop_index(op.f('ix_goals_family_id'), table_name='goals')

    op.drop_column('goals', 'family_id')
    op.drop_column('goals', 'owner_user_id')
    op.drop_column('goals', 'visibility')
