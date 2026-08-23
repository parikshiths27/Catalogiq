import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, Text

class BatchStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    partially_completed = "partially_completed"
    failed = "failed"
    cancelled = "cancelled"

class IngestionBatch(SQLModel, table=True):
    __tablename__ = "ingestion_batch"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: Optional[str] = Field(default=None, nullable=True)
    status: BatchStatus = Field(default=BatchStatus.queued, sa_column=Column(sa.String, index=True, nullable=False))
    total_files: int = Field(default=0, nullable=False)
    processed_files: int = Field(default=0, nullable=False)
    completed_files: int = Field(default=0, nullable=False)
    failed_files: int = Field(default=0, nullable=False)
    
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column("metadata", JSON))


class BatchItemStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class IngestionBatchItem(SQLModel, table=True):
    __tablename__ = "ingestion_batch_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    batch_id: uuid.UUID = Field(
        sa_column=Column(sa.Uuid, sa.ForeignKey("ingestion_batch.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    document_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("document.id", ondelete="SET NULL"), index=True, nullable=True)
    )
    job_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("processingjob.id", ondelete="SET NULL"), index=True, nullable=True)
    )
    status: BatchItemStatus = Field(default=BatchItemStatus.queued, sa_column=Column(sa.String, nullable=False))
    cached: bool = Field(default=False, nullable=False)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column("metadata", JSON))

