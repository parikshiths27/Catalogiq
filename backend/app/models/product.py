import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column
import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, UniqueConstraint

class ProductStatus(str, Enum):
    draft = "draft"
    needs_review = "needs_review"
    verified = "verified"

class Product(SQLModel, table=True):
    # Uniqueness constraint: SKU is unique within a specific brand catalog
    __table_args__ = (
        UniqueConstraint("brand", "sku", name="uq_product_brand_sku"),
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sku: str = Field(index=True, nullable=False)
    brand: str = Field(index=True, nullable=False)
    product_name: str = Field(nullable=False)
    model: Optional[str] = Field(default=None, nullable=True)
    category: str = Field(index=True, nullable=False)
    subcategory: Optional[str] = Field(default=None, nullable=True)
    product_type: Optional[str] = Field(default=None, nullable=True)
    description: Optional[str] = Field(default=None, nullable=True)
    commerce_description: Optional[str] = Field(default=None, nullable=True)
    status: ProductStatus = Field(default=ProductStatus.draft, sa_column=Column(sa.String, index=True, nullable=False))
    quality_score: float = Field(default=0.0, index=True, nullable=False)
    
    # JSONB dynamic industrial attributes & lists (features, apps, certs)
    attributes: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    features: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    applications: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    certifications: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    keywords: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True, nullable=False)
    )


class ProductListItem(SQLModel):
    id: uuid.UUID
    product_name: str
    brand: str
    sku: str
    category: str
    status: str
    quality_score: float
    updated_at: datetime

