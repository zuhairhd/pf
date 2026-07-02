"""Add import job tables

Revision ID: 9ee380da96d5
Revises: 542823443f9e
Create Date: 2026-07-02 15:21:15.136467

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9ee380da96d5'
down_revision: Union[str, Sequence[str], None] = '542823443f9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_policy_sql(table: str) -> str:
    """Return RLS policy definitions for a tenant-scoped table."""
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

    CREATE POLICY {table}_tenant_select ON {table}
        FOR SELECT
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_insert ON {table}
        FOR INSERT
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_update ON {table}
        FOR UPDATE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);

    CREATE POLICY {table}_tenant_delete ON {table}
        FOR DELETE
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER);
    """


def upgrade() -> None:
    """Upgrade schema."""
    # Import job table.
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('import_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('total_rows', sa.Integer(), nullable=False),
        sa.Column('valid_rows', sa.Integer(), nullable=False),
        sa.Column('invalid_rows', sa.Integer(), nullable=False),
        sa.Column('duplicate_rows', sa.Integer(), nullable=False),
        sa.Column('imported_rows', sa.Integer(), nullable=False),
        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_import_jobs_file_hash'), 'import_jobs', ['file_hash'], unique=False)
    op.create_index(op.f('ix_import_jobs_id'), 'import_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_import_jobs_tenant_id'), 'import_jobs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_import_jobs_user_id'), 'import_jobs', ['user_id'], unique=False)

    # Imported row table.
    op.create_table(
        'imported_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('import_job_id', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('parsed_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('duplicate_key', sa.String(length=255), nullable=True),
        sa.Column('duplicate_of_row_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['duplicate_of_row_id'], ['imported_rows.id']),
        sa.ForeignKeyConstraint(['import_job_id'], ['import_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sqlite_autoincrement=True
    )
    op.create_index(op.f('ix_imported_rows_duplicate_key'), 'imported_rows', ['duplicate_key'], unique=False)
    op.create_index(op.f('ix_imported_rows_id'), 'imported_rows', ['id'], unique=False)
    op.create_index(op.f('ix_imported_rows_import_job_id'), 'imported_rows', ['import_job_id'], unique=False)
    op.create_index(op.f('ix_imported_rows_tenant_id'), 'imported_rows', ['tenant_id'], unique=False)

    # RLS for both tables.
    op.execute(_rls_policy_sql('import_jobs'))
    op.execute(_rls_policy_sql('imported_rows'))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS import_jobs_tenant_select ON import_jobs")
    op.execute("DROP POLICY IF EXISTS import_jobs_tenant_insert ON import_jobs")
    op.execute("DROP POLICY IF EXISTS import_jobs_tenant_update ON import_jobs")
    op.execute("DROP POLICY IF EXISTS import_jobs_tenant_delete ON import_jobs")
    op.execute("ALTER TABLE import_jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_jobs DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS imported_rows_tenant_select ON imported_rows")
    op.execute("DROP POLICY IF EXISTS imported_rows_tenant_insert ON imported_rows")
    op.execute("DROP POLICY IF EXISTS imported_rows_tenant_update ON imported_rows")
    op.execute("DROP POLICY IF EXISTS imported_rows_tenant_delete ON imported_rows")
    op.execute("ALTER TABLE imported_rows NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE imported_rows DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f('ix_imported_rows_tenant_id'), table_name='imported_rows')
    op.drop_index(op.f('ix_imported_rows_import_job_id'), table_name='imported_rows')
    op.drop_index(op.f('ix_imported_rows_id'), table_name='imported_rows')
    op.drop_index(op.f('ix_imported_rows_duplicate_key'), table_name='imported_rows')
    op.drop_table('imported_rows')

    op.drop_index(op.f('ix_import_jobs_user_id'), table_name='import_jobs')
    op.drop_index(op.f('ix_import_jobs_tenant_id'), table_name='import_jobs')
    op.drop_index(op.f('ix_import_jobs_id'), table_name='import_jobs')
    op.drop_index(op.f('ix_import_jobs_file_hash'), table_name='import_jobs')
    op.drop_table('import_jobs')
