"""Add IngestionBatch model and batch_id foreign keys to document and processingjob

Revision ID: 7a645f04df90
Revises: 6f534f03ce89
Create Date: 2026-08-12 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '7a645f04df90'
down_revision: Union[str, None] = '6f534f03ce89'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create ingestion_batch table if not exists
    if 'ingestion_batch' not in tables:
        op.create_table(
            'ingestion_batch',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('total_files', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('processed_files', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('completed_files', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('failed_files', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('metadata', sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )

    # 2. Add batch_id to document table if not exists
    doc_cols = [c['name'] for c in inspector.get_columns('document')]
    if 'batch_id' not in doc_cols:
        op.add_column(
            'document',
            sa.Column('batch_id', sa.Uuid(), sa.ForeignKey('ingestion_batch.id', ondelete='SET NULL'), nullable=True)
        )
        op.create_index('ix_document_batch_id', 'document', ['batch_id'], unique=False)

    # 3. Add batch_id to processingjob table if not exists
    job_cols = [c['name'] for c in inspector.get_columns('processingjob')]
    if 'batch_id' not in job_cols:
        op.add_column(
            'processingjob',
            sa.Column('batch_id', sa.Uuid(), sa.ForeignKey('ingestion_batch.id', ondelete='SET NULL'), nullable=True)
        )
        op.create_index('ix_processingjob_batch_id', 'processingjob', ['batch_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'processingjob' in tables:
        job_cols = [c['name'] for c in inspector.get_columns('processingjob')]
        if 'batch_id' in job_cols:
            op.drop_index('ix_processingjob_batch_id', table_name='processingjob')
            op.drop_constraint('processingjob_batch_id_fkey', 'processingjob', type_='foreignkey')
            op.drop_column('processingjob', 'batch_id')

    if 'document' in tables:
        doc_cols = [c['name'] for c in inspector.get_columns('document')]
        if 'batch_id' in doc_cols:
            op.drop_index('ix_document_batch_id', table_name='document')
            op.drop_constraint('document_batch_id_fkey', 'document', type_='foreignkey')
            op.drop_column('document', 'batch_id')

    if 'ingestion_batch' in tables:
        op.drop_table('ingestion_batch')
