import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select, func, text
from sqlalchemy import or_, and_, desc
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
    """
    # 1. Product Totals & Status Breakdown
    all_products = session.exec(select(Product)).all()
    total_products = len(all_products)

    verified_count = sum(1 for p in all_products if p.status == ProductStatus.verified)
    needs_review_count = sum(1 for p in all_products if p.status == ProductStatus.needs_review)
    draft_count = sum(1 for p in all_products if p.status == ProductStatus.draft)

    avg_quality = (sum(p.quality_score for p in all_products) / total_products) if total_products > 0 else 0.0
    quality_score_overall = round(avg_quality, 1)

    verification_rate = round((verified_count / total_products) * 100.0, 1) if total_products > 0 else 0.0

    # 2. Document & Attribute Totals
    total_documents = session.exec(select(func.count()).select_from(Document)).one() or 0

    all_attributes = session.exec(select(ProductAttribute)).all()
    total_attributes = len(all_attributes)

    # 3. Evidence Coverage Rate
    ev_attr_rows = session.exec(select(AttributeEvidence.attribute_id)).all()
    evidence_attr_ids: Set[uuid.UUID] = {r for r in ev_attr_rows if r is not None}
    supported_attr_count = len({a.id for a in all_attributes if a.id in evidence_attr_ids})
    evidence_coverage = (
        round((supported_attr_count / total_attributes) * 100.0, 1)
        if total_attributes > 0
        else 0.0
    )

    # 4. Map Product Attributes & Evidence for per-product Completeness calculation
    product_attrs_map: Dict[uuid.UUID, Set[str]] = {}
    product_ev_attrs_map: Dict[uuid.UUID, Set[str]] = {}

    for attr in all_attributes:
        product_attrs_map.setdefault(attr.product_id, set()).add(attr.attribute_name)
        if attr.id in evidence_attr_ids:
            product_ev_attrs_map.setdefault(attr.product_id, set()).add(attr.attribute_name)

    completeness_calc = CompletenessCalculator()
    product_completeness_map: Dict[uuid.UUID, float] = {}

    for prod in all_products:
        p_attrs = product_attrs_map.get(prod.id, set())
        p_ev_attrs = product_ev_attrs_map.get(prod.id, set())
        c_res = completeness_calc.calculate(
            category=prod.category,
            present_attributes=p_attrs,
            evidence_supported_attributes=p_ev_attrs,
        )
        product_completeness_map[prod.id] = c_res.completeness_score

    overall_completeness_rate = (
        round(sum(product_completeness_map.values()) / total_products, 1)
        if total_products > 0
        else 0.0
    )

    # 5. Open Validation Issues & Issues Summary
    open_val_results = session.exec(
        select(ValidationResult).where(ValidationResult.status == ValidationStatus.open)
    ).all()

    total_open_issues = len(open_val_results)
    conflict_val_types = {
        ValidationType.cross_attribute_conflict.value,
        ValidationType.cross_source_conflict.value,
        ValidationType.inconsistent_value.value,
    }
    missing_val_types = {
        ValidationType.missing_required_field.value,
        ValidationType.missing_required_attribute.value,
    }

    val_conflicts_count = 0
    missing_req_count = 0
    val_issues_count = 0

    for ov in open_val_results:
        vt_str = (
            ov.validation_type.value
            if hasattr(ov.validation_type, "value")
            else str(ov.validation_type)
        )
        if vt_str in conflict_val_types:
            val_conflicts_count += 1
        elif vt_str in missing_val_types:
            missing_req_count += 1
        else:
            val_issues_count += 1

    attr_conflicts_count = sum(1 for a in all_attributes if a.status == AttributeStatus.conflicting)
    total_cross_source_conflicts = val_conflicts_count + attr_conflicts_count

    low_confidence_attrs_count = sum(
        1
        for a in all_attributes
        if (a.confidence is not None and a.confidence < 0.75)
        or a.status in (AttributeStatus.needs_review, AttributeStatus.conflicting)
    )

    # Pre-map issues and conflict flags per product
    product_issues_map: Dict[uuid.UUID, List[ValidationResult]] = {}
    for ov in open_val_results:
        product_issues_map.setdefault(ov.product_id, []).append(ov)

    # 6. Category Health Aggregates
    cat_products_map: Dict[str, List[Product]] = {}
    for p in all_products:
        cat_products_map.setdefault(p.category, []).append(p)

    category_health_items: List[CategoryHealthItemSchema] = []

    for cat_name, cat_prods in cat_products_map.items():
        c_count = len(cat_prods)
        c_avg_q = round(sum(p.quality_score for p in cat_prods) / c_count, 1) if c_count > 0 else 0.0
        c_ver_count = sum(1 for p in cat_prods if p.status == ProductStatus.verified)
        c_ver_rate = round((c_ver_count / c_count) * 100.0, 1) if c_count > 0 else 0.0
        c_comp_rate = round(sum(product_completeness_map.get(p.id, 0.0) for p in cat_prods) / c_count, 1) if c_count > 0 else 0.0

        c_open_issues = 0
        c_conflicts = 0
        for p in cat_prods:
            p_issues = product_issues_map.get(p.id, [])
            c_open_issues += len(p_issues)
            for iss in p_issues:
                vt_s = iss.validation_type.value if hasattr(iss.validation_type, "value") else str(iss.validation_type)
                if vt_s in conflict_val_types:
                    c_conflicts += 1
            # Check attribute conflicts
            p_attrs = [a for a in all_attributes if a.product_id == p.id]
            c_conflicts += sum(1 for a in p_attrs if a.status == AttributeStatus.conflicting)

        category_health_items.append(
            CategoryHealthItemSchema(
                category=cat_name,
                product_count=c_count,
                avg_quality_score=c_avg_q,
                verification_rate=c_ver_rate,
                completeness_rate=c_comp_rate,
                open_issues_count=c_open_issues,
                conflicts_count=c_conflicts,
            )
        )

    category_health_items.sort(key=lambda x: x.product_count, reverse=True)

    # 7. Brand Health Aggregates
    brand_products_map: Dict[str, List[Product]] = {}
    for p in all_products:
        brand_products_map.setdefault(p.brand, []).append(p)

    brand_health_items: List[BrandHealthItemSchema] = []

    for b_name, b_prods in brand_products_map.items():
        b_count = len(b_prods)
        b_avg_q = round(sum(p.quality_score for p in b_prods) / b_count, 1) if b_count > 0 else 0.0
        b_ver_count = sum(1 for p in b_prods if p.status == ProductStatus.verified)
        b_ver_rate = round((b_ver_count / b_count) * 100.0, 1) if b_count > 0 else 0.0
        b_comp_rate = round(sum(product_completeness_map.get(p.id, 0.0) for p in b_prods) / b_count, 1) if b_count > 0 else 0.0

        b_open_issues = 0
        b_conflicts = 0
        for p in b_prods:
            p_issues = product_issues_map.get(p.id, [])
            b_open_issues += len(p_issues)
            for iss in p_issues:
                vt_s = iss.validation_type.value if hasattr(iss.validation_type, "value") else str(iss.validation_type)
                if vt_s in conflict_val_types:
                    b_conflicts += 1
            p_attrs = [a for a in all_attributes if a.product_id == p.id]
            b_conflicts += sum(1 for a in p_attrs if a.status == AttributeStatus.conflicting)

        brand_health_items.append(
            BrandHealthItemSchema(
                brand=b_name,
                product_count=b_count,
                avg_quality_score=b_avg_q,
                verification_rate=b_ver_rate,
                completeness_rate=b_comp_rate,
                open_issues_count=b_open_issues,
                conflicts_count=b_conflicts,
            )
        )

    brand_health_items.sort(key=lambda x: x.product_count, reverse=True)

    # 8. Helper to build ProductAttentionItemSchema
    def build_attention_item(p: Product) -> ProductAttentionItemSchema:
        p_issues = product_issues_map.get(p.id, [])
        open_count = len(p_issues)
        has_conf = any(
            (iss.validation_type.value if hasattr(iss.validation_type, "value") else str(iss.validation_type)) in conflict_val_types
            for iss in p_issues
        ) or any(a.status == AttributeStatus.conflicting for a in all_attributes if a.product_id == p.id)

        missing_count = sum(
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
            missing_required_count=missing_count,
            updated_at=p.updated_at,
        )

    # 9. Products Needing Attention (Max 10)
    attention_candidates = [
        p for p in all_products
        if p.status == ProductStatus.needs_review or p.quality_score < 70.0 or len(product_issues_map.get(p.id, [])) > 0
    ]

    # Sort priority: 1) status==needs_review, 2) has_conflicts, 3) quality_score ASC, 4) open_issues_count DESC
    attention_candidates.sort(
        key=lambda p: (
            0 if p.status == ProductStatus.needs_review else 1,
            0 if build_attention_item(p).has_conflicts else 1,
            p.quality_score,
            -len(product_issues_map.get(p.id, [])),
        )
    )

    products_needing_attention = [build_attention_item(p) for p in attention_candidates[:10]]

    # 10. Worst Products (Max 10)
    worst_candidates = sorted(all_products, key=lambda p: (p.quality_score, -p.updated_at.timestamp()))
    worst_products = [build_attention_item(p) for p in worst_candidates[:10]]

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
