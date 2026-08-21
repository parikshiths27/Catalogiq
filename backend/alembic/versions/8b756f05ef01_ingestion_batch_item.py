"""Add IngestionBatchItem table and backfill historical batch relationships

Revision ID: 8b756f05ef01
Revises: 7a645f04df90
Create Date: 2026-08-12 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '8b756f05ef01'
down_revision: Union[str, None] = '7a645f04df90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. Create ingestion_batch_item table if not exists
    if 'ingestion_batch_item' not in tables:
        op.create_table(
            'ingestion_batch_item',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('batch_id', sa.Uuid(), sa.ForeignKey('ingestion_batch.id', ondelete='CASCADE'), nullable=False),
            sa.Column('document_id', sa.Uuid(), sa.ForeignKey('document.id', ondelete='SET NULL'), nullable=True),
            sa.Column('job_id', sa.Uuid(), sa.ForeignKey('processingjob.id', ondelete='SET NULL'), nullable=True),
            sa.Column('status', sa.String(), nullable=False, server_default='queued'),
            sa.Column('cached', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('metadata', sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )

        op.create_index('ix_ingestion_batch_item_batch_id', 'ingestion_batch_item', ['batch_id'], unique=False)
        op.create_index('ix_ingestion_batch_item_document_id', 'ingestion_batch_item', ['document_id'], unique=False)
        op.create_index('ix_ingestion_batch_item_job_id', 'ingestion_batch_item', ['job_id'], unique=False)

    # 2. Backfill historical document.batch_id links into ingestion_batch_item
    op.execute(
        """
        INSERT INTO ingestion_batch_item (id, batch_id, document_id, job_id, status, cached, created_at, updated_at)
        SELECT 
            gen_random_uuid(),
            d.batch_id,
            d.id,
            (
                SELECT ps.job_id 
                FROM processingstep ps 
                WHERE ps.document_id = d.id 
                ORDER BY ps.created_at DESC 
                LIMIT 1
            ) AS job_id,
            CASE 
                WHEN d.status = 'processed' THEN 'completed'
                WHEN d.status = 'failed' THEN 'failed'
                ELSE 'processing'
            END,
            false,
            d.created_at,
            d.updated_at
        FROM document d
        WHERE d.batch_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM ingestion_batch_item bi 
            WHERE bi.batch_id = d.batch_id AND bi.document_id = d.id
        );
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'ingestion_batch_item' in tables:
        op.drop_index('ix_ingestion_batch_item_job_id', table_name='ingestion_batch_item')
        op.drop_index('ix_ingestion_batch_item_document_id', table_name='ingestion_batch_item')
        op.drop_index('ix_ingestion_batch_item_batch_id', table_name='ingestion_batch_item')
        op.drop_table('ingestion_batch_item')
