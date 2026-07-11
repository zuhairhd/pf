"""harden document model for upload ocr and linking

Revision ID: 5e8169dd3017
Revises: 33f87e4863be
Create Date: 2026-07-11 08:03:51.709134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e8169dd3017'
down_revision: Union[str, Sequence[str], None] = '33f87e4863be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Document model hardening
    op.add_column('documents', sa.Column('filename_stored', sa.String(length=255), nullable=True))
    op.add_column('documents', sa.Column('category', sa.String(length=50), nullable=True))
    op.add_column('documents', sa.Column('checksum', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True))
    op.add_column(
        'documents',
        sa.Column('status', sa.String(length=20), nullable=False, server_default='uploaded')
    )
    op.add_column('documents', sa.Column('ocr_status', sa.String(length=20), nullable=True))
    op.add_column('documents', sa.Column('ocr_error', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('related_entity_type', sa.String(length=50), nullable=True))
    op.add_column('documents', sa.Column('related_entity_id', sa.Integer(), nullable=True))

    # Backfill filename_stored from existing filename for any pre-existing rows.
    op.execute("UPDATE documents SET filename_stored = filename WHERE filename_stored IS NULL")

    # Indexes
    op.create_index(op.f('ix_documents_category'), 'documents', ['category'], unique=False)
    op.create_index(op.f('ix_documents_checksum'), 'documents', ['checksum'], unique=False)
    op.create_index(op.f('ix_documents_related_entity_id'), 'documents', ['related_entity_id'], unique=False)
    op.create_index(op.f('ix_documents_related_entity_type'), 'documents', ['related_entity_type'], unique=False)
    op.create_index(op.f('ix_documents_status'), 'documents', ['status'], unique=False)
    op.create_index('ix_documents_tenant_related_entity', 'documents', ['tenant_id', 'related_entity_type', 'related_entity_id'], unique=False)
    op.create_index('ix_documents_tenant_status', 'documents', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_documents_tenant_uploader', 'documents', ['tenant_id', 'uploaded_by_user_id'], unique=False)
    op.create_index(op.f('ix_documents_uploaded_by_user_id'), 'documents', ['uploaded_by_user_id'], unique=False)

    # Foreign key to uploader
    op.create_foreign_key(
        op.f('fk_documents_uploaded_by_user_id_users'),
        'documents',
        'users',
        ['uploaded_by_user_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('fk_documents_uploaded_by_user_id_users'), 'documents', type_='foreignkey')
    op.drop_index(op.f('ix_documents_uploaded_by_user_id'), table_name='documents')
    op.drop_index('ix_documents_tenant_uploader', table_name='documents')
    op.drop_index('ix_documents_tenant_status', table_name='documents')
    op.drop_index('ix_documents_tenant_related_entity', table_name='documents')
    op.drop_index(op.f('ix_documents_status'), table_name='documents')
    op.drop_index(op.f('ix_documents_related_entity_type'), table_name='documents')
    op.drop_index(op.f('ix_documents_related_entity_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_checksum'), table_name='documents')
    op.drop_index(op.f('ix_documents_category'), table_name='documents')
    op.drop_column('documents', 'related_entity_id')
    op.drop_column('documents', 'related_entity_type')
    op.drop_column('documents', 'ocr_error')
    op.drop_column('documents', 'ocr_status')
    op.drop_column('documents', 'status')
    op.drop_column('documents', 'uploaded_by_user_id')
    op.drop_column('documents', 'checksum')
    op.drop_column('documents', 'category')
    op.drop_column('documents', 'filename_stored')
