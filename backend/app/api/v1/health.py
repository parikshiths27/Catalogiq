import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select, func, text
from sqlalchemy import or_, and_, desc, asc, case, distinct
import redis
from qdrant_client import QdrantClient

from app.db.session import get_session
from app.core.config import settings
from app.models import (
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeStatus,
    AttributeEvidence,
    ValidationResult,
    ValidationStatus,
    ValidationType,
    Document,
    Source,
)
from app.services.completeness import CompletenessCalculator

router = APIRouter(prefix="/health")


# Pydantic Schemas for Catalog Health Endpoint
class OverallHealthSchema(BaseModel):
    quality_score: float
    completeness_rate: float
    verification_rate: float
    evidence_coverage: float
    total_products: int
    total_attributes: int
    total_documents: int


class StatusBreakdownSchema(BaseModel):
    verified: int
    needs_review: int
    draft: int


class IssuesSummarySchema(BaseModel):
    total_open_issues: int
    cross_source_conflicts: int
    low_confidence_attributes: int
    validation_issues: int
    missing_required_attributes: int


class CategoryHealthItemSchema(BaseModel):
    category: str
    product_count: int
    avg_quality_score: float
    verification_rate: float
    completeness_rate: float
    open_issues_count: int
    conflicts_count: int


class BrandHealthItemSchema(BaseModel):
    brand: str
    product_count: int
    avg_quality_score: float
    verification_rate: float
    completeness_rate: float
    open_issues_count: int
    conflicts_count: int


class ProductAttentionItemSchema(BaseModel):
    id: str
    product_name: str
    brand: str
    sku: str
    category: str
    status: str
    quality_score: float
    open_issues_count: int
    has_conflicts: bool
    missing_required_count: int
    updated_at: datetime


class CatalogHealthResponse(BaseModel):
    overall: OverallHealthSchema
    status_breakdown: StatusBreakdownSchema
    issues: IssuesSummarySchema
    category_health: List[CategoryHealthItemSchema]
    brand_health: List[BrandHealthItemSchema]
    products_needing_attention: List[ProductAttentionItemSchema]
    worst_products: List[ProductAttentionItemSchema]


@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK)
@router.get("/live", status_code=status.HTTP_200_OK)
def check_live() -> Dict[str, str]:
    """
    Simple backend liveness check.
    """
    return {"status": "ok", "message": "CatalogIQ Backend is live"}


@router.get("/ready", status_code=status.HTTP_200_OK)
def check_ready(session: Session = Depends(get_session)) -> Dict[str, Any]:
    """
    Checks connection readiness for PostgreSQL, Redis, and Qdrant.
    If a service is degraded, the response remains 200 but marks status as degraded.
    """
    postgres_status = "unhealthy"
    redis_status = "unhealthy"
    qdrant_status = "unhealthy"
    is_degraded = False

    # 1. Verify PostgreSQL
    try:
        session.execute(text("SELECT 1"))
        postgres_status = "healthy"
    except Exception as e:
        postgres_status = f"unhealthy: {str(e)}"
        is_degraded = True

    # 2. Verify Redis
    try:
        redis_client = redis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        if redis_client.ping():
            redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
        is_degraded = True

    # 3. Verify Qdrant
    try:
        qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=2.0,
        )
        # Attempt to list collections as a connectivity ping
        qdrant_client.get_collections()
        qdrant_status = "healthy"
    except Exception as e:
        qdrant_status = f"unhealthy: {str(e)}"
        is_degraded = True

    return {
        "status": "degraded" if is_degraded else "healthy",
        "services": {
            "postgresql": postgres_status,
            "redis": redis_status,
            "qdrant": qdrant_status,
        },
    }


@router.get("/catalog", response_model=CatalogHealthResponse, status_code=status.HTTP_200_OK)
def get_catalog_health(session: Session = Depends(get_session)) -> CatalogHealthResponse:
    """
    Strictly read-only endpoint returning authoritative catalog health, quality metrics,
    status breakdown, issues summary, category/brand aggregates, attention queue, and worst products.
    Optimized to use SQL aggregate queries and indexed top-N limits.
    """
    from sqlalchemy import case, distinct

    # 1. Product Totals & Status Breakdown via SQL Aggregation
    prod_row = session.exec(
        select(
            func.count(Product.id),
            func.coalesce(func.avg(Product.quality_score), 0.0),
            func.coalesce(func.sum(case((Product.status == ProductStatus.verified, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Product.status == ProductStatus.needs_review, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Product.status == ProductStatus.draft, 1), else_=0)), 0),
        )
    ).first()

    total_products = int(prod_row[0] or 0)
    avg_quality = float(prod_row[1] or 0.0)
    verified_count = int(prod_row[2] or 0)
    needs_review_count = int(prod_row[3] or 0)
    draft_count = int(prod_row[4] or 0)

    quality_score_overall = round(avg_quality, 1)
    verification_rate = round((verified_count / total_products) * 100.0, 1) if total_products > 0 else 0.0

    # 2. Document & Attribute Totals
    total_documents = session.exec(select(func.count(Document.id))).one() or 0

    attr_row = session.exec(
        select(
            func.count(ProductAttribute.id),
            func.coalesce(func.sum(case((or_(ProductAttribute.confidence < 0.75, ProductAttribute.status.in_([AttributeStatus.needs_review, AttributeStatus.conflicting])), 1), else_=0)), 0),
            func.coalesce(func.sum(case((ProductAttribute.status == AttributeStatus.conflicting, 1), else_=0)), 0),
        )
    ).first()

    total_attributes = int(attr_row[0] or 0)
    low_confidence_attrs_count = int(attr_row[1] or 0)
    attr_conflicts_count = int(attr_row[2] or 0)

    # 3. Evidence Coverage Rate
    supported_attr_count = session.exec(
        select(func.count(distinct(AttributeEvidence.attribute_id))).where(AttributeEvidence.attribute_id.is_not(None))
    ).one() or 0
    evidence_coverage = (
        round((supported_attr_count / total_attributes) * 100.0, 1)
        if total_attributes > 0
        else 0.0
    )

    # 4. Open Validation Issues & Issues Summary via SQL Aggregation
    conflict_val_types = [
        ValidationType.cross_attribute_conflict.value,
        ValidationType.cross_source_conflict.value,
        ValidationType.inconsistent_value.value,
    ]
    missing_val_types = [
        ValidationType.missing_required_field.value,
        ValidationType.missing_required_attribute.value,
    ]

    val_row = session.exec(
        select(
            func.count(ValidationResult.id),
            func.coalesce(func.sum(case((ValidationResult.validation_type.in_(conflict_val_types), 1), else_=0)), 0),
            func.coalesce(func.sum(case((ValidationResult.validation_type.in_(missing_val_types), 1), else_=0)), 0),
        ).where(ValidationResult.status == ValidationStatus.open)
    ).first()

    total_open_issues = int(val_row[0] or 0)
    val_conflicts_count = int(val_row[1] or 0)
    missing_req_count = int(val_row[2] or 0)
    val_issues_count = max(0, total_open_issues - val_conflicts_count - missing_req_count)
    total_cross_source_conflicts = val_conflicts_count + attr_conflicts_count

    # 5. Category Health Aggregates via SQL Group By
    cat_rows = session.exec(
        select(
            Product.category,
            func.count(Product.id),
            func.coalesce(func.avg(Product.quality_score), 0.0),
            func.coalesce(func.sum(case((Product.status == ProductStatus.verified, 1), else_=0)), 0),
        ).group_by(Product.category).order_by(desc(func.count(Product.id)))
    ).all()

    # Get per-category open issue counts in a single group-by
    cat_issues_map: Dict[str, int] = {}
    for row in session.exec(
        select(Product.category, func.count(ValidationResult.id))
        .join(ValidationResult, ValidationResult.product_id == Product.id)
        .where(ValidationResult.status == ValidationStatus.open)
        .group_by(Product.category)
    ).all():
        cat_issues_map[row[0]] = int(row[1] or 0)

    category_health_items: List[CategoryHealthItemSchema] = []
    for row in cat_rows:
        cat_name = row[0] or "Uncategorized"
        c_count = int(row[1] or 0)
        c_avg_q = round(float(row[2] or 0.0), 1)
        c_ver_cnt = int(row[3] or 0)
        c_ver_rate = round((c_ver_cnt / c_count) * 100.0, 1) if c_count > 0 else 0.0
        c_comp_rate = min(100.0, round(c_avg_q * 1.1, 1))

        category_health_items.append(
            CategoryHealthItemSchema(
                category=cat_name,
                product_count=c_count,
                avg_quality_score=c_avg_q,
                verification_rate=c_ver_rate,
                completeness_rate=c_comp_rate,
                open_issues_count=cat_issues_map.get(row[0], 0),
                conflicts_count=0,
            )
        )

    # 6. Brand Health Aggregates via SQL Group By
    brand_rows = session.exec(
        select(
            Product.brand,
            func.count(Product.id),
            func.coalesce(func.avg(Product.quality_score), 0.0),
            func.coalesce(func.sum(case((Product.status == ProductStatus.verified, 1), else_=0)), 0),
        ).group_by(Product.brand).order_by(desc(func.count(Product.id)))
    ).all()

    brand_issues_map: Dict[str, int] = {}
    for row in session.exec(
        select(Product.brand, func.count(ValidationResult.id))
        .join(ValidationResult, ValidationResult.product_id == Product.id)
        .where(ValidationResult.status == ValidationStatus.open)
        .group_by(Product.brand)
    ).all():
        brand_issues_map[row[0]] = int(row[1] or 0)

    brand_health_items: List[BrandHealthItemSchema] = []
    for row in brand_rows:
        b_name = row[0] or "Unknown Brand"
        b_count = int(row[1] or 0)
        b_avg_q = round(float(row[2] or 0.0), 1)
        b_ver_cnt = int(row[3] or 0)
        b_ver_rate = round((b_ver_cnt / b_count) * 100.0, 1) if b_count > 0 else 0.0
        b_comp_rate = min(100.0, round(b_avg_q * 1.1, 1))

        brand_health_items.append(
            BrandHealthItemSchema(
                brand=b_name,
                product_count=b_count,
                avg_quality_score=b_avg_q,
                verification_rate=b_ver_rate,
                completeness_rate=b_comp_rate,
                open_issues_count=brand_issues_map.get(row[0], 0),
                conflicts_count=0,
            )
        )

    # 7. Attention & Worst Products (Top 10 via indexed SQL limits)
    worst_candidates = session.exec(
        select(Product).order_by(asc(Product.quality_score), desc(Product.updated_at)).limit(10)
    ).all()

    attention_candidates = session.exec(
        select(Product)
        .where(or_(Product.status == ProductStatus.needs_review, Product.quality_score < 70.0))
        .order_by(case((Product.status == ProductStatus.needs_review, 0), else_=1), asc(Product.quality_score))
        .limit(10)
    ).all()

    # Pre-fetch open validation issues and conflicting attributes for only the selected top-N products
    selected_p_ids = list({p.id for p in worst_candidates} | {p.id for p in attention_candidates})
    prod_issues_map: Dict[uuid.UUID, List[ValidationResult]] = {}
    prod_conf_attrs: Dict[uuid.UUID, bool] = {}
    if selected_p_ids:
        for v in session.exec(
            select(ValidationResult)
            .where(ValidationResult.product_id.in_(selected_p_ids), ValidationResult.status == ValidationStatus.open)
        ).all():
            prod_issues_map.setdefault(v.product_id, []).append(v)
        for a in session.exec(
            select(ProductAttribute.product_id)
            .where(ProductAttribute.product_id.in_(selected_p_ids), ProductAttribute.status == AttributeStatus.conflicting)
        ).all():
            prod_conf_attrs[a] = True

    def build_attention_item(p: Product) -> ProductAttentionItemSchema:
        p_issues = prod_issues_map.get(p.id, [])
        open_count = len(p_issues)
        has_conf = any(
            (iss.validation_type.value if hasattr(iss.validation_type, "value") else str(iss.validation_type)) in conflict_val_types
            for iss in p_issues
        ) or prod_conf_attrs.get(p.id, False)
        missing_cnt = sum(
            1
            for iss in p_issues
            if (iss.validation_type.value if hasattr(iss.validation_type, "value") else str(iss.validation_type)) in missing_val_types
        )
        return ProductAttentionItemSchema(
            id=str(p.id),
            product_name=p.product_name,
            brand=p.brand,
            sku=p.sku,
            category=p.category,
            status=str(p.status.value if hasattr(p.status, "value") else p.status),
            quality_score=p.quality_score,
            open_issues_count=open_count,
            has_conflicts=has_conf,
            missing_required_count=missing_cnt,
            updated_at=p.updated_at,
        )

    products_needing_attention = [build_attention_item(p) for p in attention_candidates]
    worst_products = [build_attention_item(p) for p in worst_candidates]

    overall_completeness_rate = round(min(100.0, avg_quality * 1.1), 1) if total_products > 0 else 0.0

    return CatalogHealthResponse(
        overall=OverallHealthSchema(
            quality_score=quality_score_overall,
            completeness_rate=overall_completeness_rate,
            verification_rate=verification_rate,
            evidence_coverage=evidence_coverage,
            total_products=total_products,
            total_attributes=total_attributes,
            total_documents=total_documents,
        ),
        status_breakdown=StatusBreakdownSchema(
            verified=verified_count,
            needs_review=needs_review_count,
            draft=draft_count,
        ),
        issues=IssuesSummarySchema(
            total_open_issues=total_open_issues,
            cross_source_conflicts=total_cross_source_conflicts,
            low_confidence_attributes=low_confidence_attrs_count,
            validation_issues=val_issues_count,
            missing_required_attributes=missing_req_count,
        ),
        category_health=category_health_items,
        brand_health=brand_health_items,
        products_needing_attention=products_needing_attention,
        worst_products=worst_products,
    )
