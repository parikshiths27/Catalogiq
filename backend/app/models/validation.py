import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, Text

class ValidationType(str, Enum):
    missing_required_field = "missing_required_field"
    missing_required_attribute = "missing_required_attribute"
    invalid_value = "invalid_value"
    invalid_type = "invalid_type"
    invalid_unit = "invalid_unit"
    invalid_numeric_value = "invalid_numeric_value"
    unit_inconsistency = "unit_inconsistency"
    out_of_range = "out_of_range"
    cross_attribute_conflict = "cross_attribute_conflict"
    cross_source_conflict = "cross_source_conflict"
    inconsistent_value = "inconsistent_value"
    suspicious_value = "suspicious_value"
    duplicate_risk = "duplicate_risk"
    duplicate_product = "duplicate_product"
    low_confidence = "low_confidence"
    unsupported_claim = "unsupported_claim"
    manufacturer_unresolved = "manufacturer_unresolved"
    brand_unresolved = "brand_unresolved"
    manufacturer_brand_conflict = "manufacturer_brand_conflict"
    taxonomy_unresolved = "taxonomy_unresolved"
    attribute_not_in_lov = "attribute_not_in_lov"
    attribute_ambiguous = "attribute_ambiguous"
    unsupported_uom = "unsupported_uom"
    missing_manufacturer_evidence = "missing_manufacturer_evidence"
    conflicting_sources = "conflicting_sources"
    duplicate_identity_conflict = "duplicate_identity_conflict"

class ValidationSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"

class ValidationStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    ignored = "ignored"

class ValidationResult(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(
        sa_column=Column(sa.Uuid, sa.ForeignKey("product.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    attribute_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(sa.Uuid, sa.ForeignKey("productattribute.id", ondelete="SET NULL"), nullable=True)
    )
    validation_type: ValidationType = Field(sa_column=Column(sa.String, index=True, nullable=False))
    severity: ValidationSeverity = Field(sa_column=Column(sa.String, nullable=False))
    status: ValidationStatus = Field(default=ValidationStatus.open, sa_column=Column(sa.String, index=True, nullable=False))
    message: str = Field(sa_column=Column(Text, nullable=False))
    expected_value: Optional[Any] = Field(default=None, sa_column=Column(JSON, nullable=True))
    actual_value: Optional[Any] = Field(default=None, sa_column=Column(JSON, nullable=True))
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    resolved_by: Optional[str] = Field(default=None, nullable=True)
