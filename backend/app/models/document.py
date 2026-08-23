import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime

class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    parsing = "parsing"
    processed = "processed"
    failed = "failed"

class ProductDocumentAssociation(SQLModel, table=True):
    __tablename__ = "product_document_association"
    
    product_id: uuid.UUID = Field(
        sa_column=Column(sa.Uuid, sa.ForeignKey("product.id", ondelete="CASCADE"), primary_key=True)
    )
    document_id: uuid.UUID = Field(
        sa_column=Column(sa.Uuid, sa.ForeignKey("document.id", ondelete="CASCADE"), primary_key=True)
    )

class Document(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    filename: str = Field(nullable=False)
    storage_backend: str = Field(default="local", nullable=False)  # local, s3
    storage_key: str = Field(nullable=False)  # File path/URI
    file_hash: str = Field(index=True, nullable=False)  # SHA-256 hash of file content
    content_hash: Optional[str] = Field(default=None, index=True, nullable=True)  # Optional parsed text hash
    mime_type: str = Field(nullable=False)
    file_size: int = Field(nullable=False)
    page_count: Optional[int] = Field(default=None, nullable=True)
    batch_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("ingestion_batch.id", ondelete="SET NULL"), index=True, nullable=True)
    )
    status: DocumentStatus = Field(default=DocumentStatus.uploaded, sa_column=Column(sa.String, index=True, nullable=False))
    parser_name: Optional[str] = Field(default=None, nullable=True)
    parser_version: Optional[str] = Field(default=None, nullable=True)
    parsed_storage_key: Optional[str] = Field(default=None, nullable=True)
    parsed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
