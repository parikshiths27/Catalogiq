import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime

class SourceType(str, Enum):
    # Primary UniHack Provenance Standards
    RAW_INPUT = "RAW_INPUT"                          # Distributor catalog / input CSV
    REFERENCE_MASTER = "REFERENCE_MASTER"            # Canonical master data / UniCat / LOV / UOM
    MANUFACTURER_SOURCE = "MANUFACTURER_SOURCE"      # Official manufacturer website / datasheet / manual
    DERIVED = "DERIVED"                              # Deterministically normalized / calculated
    MODEL_INFERENCE = "MODEL_INFERENCE"              # LLM extraction / generative content

    # Legacy lowercase aliases
    document = "RAW_INPUT"
    catalog = "RAW_INPUT"
    manufacturer_website = "MANUFACTURER_SOURCE"
    manual = "REFERENCE_MASTER"
    ai_inference = "MODEL_INFERENCE"
    human = "DERIVED"


class Source(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_type: SourceType = Field(sa_column=Column(sa.String, nullable=False))
    name: str = Field(nullable=False)
    uri: Optional[str] = Field(default=None, nullable=True)
    document_id: Optional[uuid.UUID] = Field(
        default=None, 
        sa_column=Column(sa.Uuid, sa.ForeignKey("document.id", ondelete="SET NULL"), nullable=True)
    )
    metadata_json: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    trust_level: float = Field(default=1.0, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
