import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, Text

class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    partially_completed = "partially_completed"
    failed = "failed"
    cancelled = "cancelled"

class ProcessingStage(str, Enum):
    uploaded = "uploaded"
    queued = "queued"
    parsing = "parsing"
    extracting = "extracting"
    normalizing = "normalizing"
    validating = "validating"
    enriching = "enriching"
    embedding = "embedding"
    completed = "completed"
    failed = "failed"

class StepStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"

class ProcessingJob(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    batch_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("ingestion_batch.id", ondelete="SET NULL"), index=True, nullable=True)
    )
    total_items: int = Field(default=0, nullable=False)
    completed_items: int = Field(default=0, nullable=False)
    failed_items: int = Field(default=0, nullable=False)
    needs_review_items: int = Field(default=0, nullable=False)
    status: JobStatus = Field(default=JobStatus.queued, sa_column=Column(sa.String, nullable=False))
    current_stage: Optional[str] = Field(default=None, nullable=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    
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

class ProcessingStep(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    job_id: uuid.UUID = Field(
        sa_column=Column(sa.Uuid, sa.ForeignKey("processingjob.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    document_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("document.id", ondelete="SET NULL"), nullable=True)
    )
    product_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("product.id", ondelete="SET NULL"), nullable=True)
    )
    stage: ProcessingStage = Field(sa_column=Column(sa.String, nullable=False))
    status: StepStatus = Field(default=StepStatus.queued, sa_column=Column(sa.String, nullable=False))
    attempt_count: int = Field(default=1, nullable=False)
    worker_id: Optional[str] = Field(default=None, nullable=True)
    input_hash: Optional[str] = Field(default=None, nullable=True)
    output_hash: Optional[str] = Field(default=None, nullable=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    
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
