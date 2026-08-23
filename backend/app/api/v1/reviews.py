import uuid
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select, func
from sqlalchemy import or_, and_, desc, asc, distinct, case

from app.db.session import get_session
from app.models import (
    AuditLog,
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeStatus,
    ValidationResult,
    ValidationStatus,
    ValidationType,
    ValidationSeverity,
    AttributeEvidence,
    Source,
    Document,
)

router = APIRouter(prefix="/reviews")


class EvidenceSummarySchema(BaseModel):
    id: str
    attribute_id: Optional[str] = None
    source_name: str = "Unknown Source"
    source_type: str = "document"
    trust_level: float = 1.0
    document_filename: Optional[str] = None
    page_number: Optional[int] = None
    evidence_text: str = ""
    extraction_method: str = "llm"


class ReviewItemSchema(BaseModel):
    validation_id: str
    product_id: str
    product_name: str
    brand: str
    sku: str
    category: str
    attribute_id: Optional[str] = None
    attribute_name: Optional[str] = None
    display_name: Optional[str] = None
    category_type: str  # "cross_source_conflict" | "low_confidence" | "validation_issue" | "missing_attribute"
    validation_type: str
    status: str
    severity: str
    message: str
    actual_value: Optional[Any] = None
    expected_value: Optional[Any] = None
    current_value: Optional[Any] = None
    confidence: Optional[float] = None
    product_quality_score: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    evidence: List[EvidenceSummarySchema] = []
    competing_claims: List[Dict[str, Any]] = []


class ReviewSummaryCountsSchema(BaseModel):
    total_open_issues: int
    total_resolved_issues: int = 0
    cross_source_conflicts: int
    low_confidence_issues: int
    validation_issues: int
    missing_required_attributes: int
    products_needing_review: int


class ReviewsListResponse(BaseModel):
    summary: ReviewSummaryCountsSchema
    items: List[ReviewItemSchema]
    total_items: int
    page: int
    limit: int
    total_pages: int


def classify_issue_category(val_type: str, attr_status: Optional[str], confidence: Optional[float]) -> str:
    conflict_types = {
        ValidationType.cross_attribute_conflict.value,
        ValidationType.cross_source_conflict.value,
        ValidationType.inconsistent_value.value,
        getattr(ValidationType, "manufacturer_brand_conflict", "manufacturer_brand_conflict"),
        getattr(ValidationType, "duplicate_identity_conflict", "duplicate_identity_conflict"),
        getattr(ValidationType, "conflicting_sources", "conflicting_sources"),
    }
    low_conf_types = {
        ValidationType.low_confidence.value,
        ValidationType.unsupported_claim.value,
        getattr(ValidationType, "missing_manufacturer_evidence", "missing_manufacturer_evidence"),
    }
    missing_types = {
        ValidationType.missing_required_field.value,
        ValidationType.missing_required_attribute.value,
        getattr(ValidationType, "manufacturer_unresolved", "manufacturer_unresolved"),
        getattr(ValidationType, "brand_unresolved", "brand_unresolved"),
        getattr(ValidationType, "taxonomy_unresolved", "taxonomy_unresolved"),
        getattr(ValidationType, "attribute_not_in_lov", "attribute_not_in_lov"),
        getattr(ValidationType, "unsupported_uom", "unsupported_uom"),
    }

    if val_type in conflict_types or attr_status == AttributeStatus.conflicting.value:
        return "cross_source_conflict"
    elif val_type in missing_types:
        return "missing_attribute"
    elif val_type in low_conf_types or (confidence is not None and confidence < 0.75) or attr_status == AttributeStatus.needs_review.value:
        return "low_confidence"
    else:
        return "validation_issue"


@router.get("", response_model=ReviewsListResponse, status_code=status.HTTP_200_OK)
@router.get("/", response_model=ReviewsListResponse, status_code=status.HTTP_200_OK)
def list_reviews(
    status_filter: str = Query("open", alias="status"),
    issue_type: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("newest"),  # "newest", "oldest", "severity", "confidence"
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> ReviewsListResponse:
    """
    Read-only endpoint returning structured review and validation records for human review workspace.
    """
    from sqlalchemy import case

    # 1. Base query for ValidationResult
    base_query = select(ValidationResult)

    if status_filter != "all":
        base_query = base_query.where(ValidationResult.status == status_filter)

    if product_id:
        try:
            p_uuid = uuid.UUID(product_id)
            base_query = base_query.where(ValidationResult.product_id == p_uuid)
        except ValueError:
            pass

    if severity:
        base_query = base_query.where(ValidationResult.severity == severity)

    # 2. Issue type filtering at query level where possible
    conflict_val_types = [
        ValidationType.cross_attribute_conflict.value,
        ValidationType.cross_source_conflict.value,
        ValidationType.inconsistent_value.value,
        "manufacturer_brand_conflict",
        "duplicate_identity_conflict",
        "conflicting_sources",
    ]
    low_conf_types = [
        ValidationType.low_confidence.value,
        ValidationType.unsupported_claim.value,
        "missing_manufacturer_evidence",
    ]
    missing_types = [
        ValidationType.missing_required_field.value,
        ValidationType.missing_required_attribute.value,
        "manufacturer_unresolved",
        "brand_unresolved",
        "taxonomy_unresolved",
        "attribute_not_in_lov",
        "unsupported_uom",
    ]

    if issue_type and issue_type != "all":
        if issue_type == "cross_source_conflict":
            base_query = base_query.where(ValidationResult.validation_type.in_(conflict_val_types))
        elif issue_type == "low_confidence":
            base_query = base_query.where(ValidationResult.validation_type.in_(low_conf_types))
        elif issue_type == "missing_attribute":
            base_query = base_query.where(ValidationResult.validation_type.in_(missing_types))
        else:
            base_query = base_query.where(ValidationResult.validation_type == issue_type)

    # Search filter
    if search:
        s_pattern = f"%{search.strip()}%"
        base_query = base_query.join(Product, Product.id == ValidationResult.product_id).where(
            or_(
                ValidationResult.message.ilike(s_pattern),
                Product.product_name.ilike(s_pattern),
                Product.sku.ilike(s_pattern),
                Product.brand.ilike(s_pattern),
            )
        )

    # Count total matching items
    count_query = select(func.count(ValidationResult.id))
    if status_filter != "all":
        count_query = count_query.where(ValidationResult.status == status_filter)
    if severity:
        count_query = count_query.where(ValidationResult.severity == severity)
    if product_id:
        try:
            count_query = count_query.where(ValidationResult.product_id == uuid.UUID(product_id))
        except ValueError:
            pass

    total_items = session.exec(select(func.count()).select_from(base_query.subquery())).one() or 0

    # Apply ordering
    if sort_by == "oldest":
        order_stmt = asc(ValidationResult.created_at)
    else:
        order_stmt = desc(ValidationResult.created_at)

    # Fetch ONLY the paginated slice
    val_results = session.exec(
        base_query.order_by(order_stmt).offset((page - 1) * limit).limit(limit)
    ).all()

    # Pre-cache related Products, Attributes, Documents, Sources ONLY for paginated slice
    product_ids = {v.product_id for v in val_results}
    attribute_ids = {v.attribute_id for v in val_results if v.attribute_id}

    products_by_id: Dict[uuid.UUID, Product] = {}
    if product_ids:
        for p in session.exec(select(Product).where(Product.id.in_(product_ids))).all():
            products_by_id[p.id] = p

    attrs_by_id: Dict[uuid.UUID, ProductAttribute] = {}
    if attribute_ids:
        for a in session.exec(select(ProductAttribute).where(ProductAttribute.id.in_(attribute_ids))).all():
            attrs_by_id[a.id] = a

    # Pre-fetch evidence records
    evidences_by_attr: Dict[uuid.UUID, List[AttributeEvidence]] = {}
    if attribute_ids:
        ev_list = session.exec(select(AttributeEvidence).where(AttributeEvidence.attribute_id.in_(attribute_ids))).all()
        for ev in ev_list:
            evidences_by_attr.setdefault(ev.attribute_id, []).append(ev)

    # Pre-fetch documents and sources
    doc_ids = {ev.document_id for evs in evidences_by_attr.values() for ev in evs if ev.document_id}
    source_ids = {ev.source_id for evs in evidences_by_attr.values() for ev in evs if ev.source_id}

    docs_by_id: Dict[uuid.UUID, Document] = {}
    if doc_ids:
        for d in session.exec(select(Document).where(Document.id.in_(doc_ids))).all():
            docs_by_id[d.id] = d

    sources_by_id: Dict[uuid.UUID, Source] = {}
    if source_ids:
        for s in session.exec(select(Source).where(Source.id.in_(source_ids))).all():
            sources_by_id[s.id] = s

    review_items: List[ReviewItemSchema] = []

    for val in val_results:
        prod = products_by_id.get(val.product_id)
        if not prod:
            continue

        attr = attrs_by_id.get(val.attribute_id) if val.attribute_id else None
        attr_status_str = attr.status.value if attr and hasattr(attr.status, "value") else (str(attr.status) if attr else None)
        attr_confidence = attr.confidence if attr else None

        val_type_str = val.validation_type.value if hasattr(val.validation_type, "value") else str(val.validation_type)
        cat_type = classify_issue_category(val_type_str, attr_status_str, attr_confidence)

        # Build evidence items
        ev_items: List[EvidenceSummarySchema] = []
        if val.attribute_id and val.attribute_id in evidences_by_attr:
            for ev in evidences_by_attr[val.attribute_id]:
                doc_obj = docs_by_id.get(ev.document_id) if ev.document_id else None
                src_obj = sources_by_id.get(ev.source_id) if ev.source_id else None

                ev_items.append(
                    EvidenceSummarySchema(
                        id=str(ev.id),
                        attribute_id=str(ev.attribute_id),
                        source_name=src_obj.name if src_obj else (doc_obj.filename if doc_obj else "Catalog Document"),
                        source_type=str(src_obj.source_type.value if src_obj and hasattr(src_obj.source_type, "value") else "document"),
                        trust_level=src_obj.trust_level if src_obj else 1.0,
                        document_filename=doc_obj.filename if doc_obj else None,
                        page_number=ev.page_number,
                        evidence_text=ev.evidence_text,
                        extraction_method=ev.extraction_method,
                    )
                )

        # Build competing claims representation
        competing_claims = []
        if val.actual_value is not None:
            competing_claims.append({
                "claim_type": "actual_extracted",
                "label": "Extracted Claim (Source A)",
                "value": val.actual_value,
                "trust_level": 0.95,
            })
        if val.expected_value is not None:
            competing_claims.append({
                "claim_type": "expected_canonical",
                "label": "Expected / Competing Claim (Source B)",
                "value": val.expected_value,
                "trust_level": 0.70,
            })

        review_items.append(
            ReviewItemSchema(
                validation_id=str(val.id),
                product_id=str(prod.id),
                product_name=prod.product_name,
                brand=prod.brand,
                sku=prod.sku,
                category=prod.category,
                attribute_id=str(attr.id) if attr else None,
                attribute_name=attr.attribute_name if attr else None,
                display_name=attr.display_name if attr else (val.attribute_id and str(val.attribute_id) or val_type_str),
                category_type=cat_type,
                validation_type=val_type_str,
                status=str(val.status.value if hasattr(val.status, "value") else val.status),
                severity=str(val.severity.value if hasattr(val.severity, "value") else val.severity),
                message=val.message,
                actual_value=val.actual_value if val.actual_value is not None else (attr.raw_value if attr else None),
                expected_value=val.expected_value,
                current_value=attr.raw_value if attr else val.actual_value,
                confidence=attr_confidence,
                product_quality_score=prod.quality_score,
                created_at=val.created_at,
                resolved_at=val.resolved_at,
                resolved_by=val.resolved_by,
                evidence=ev_items,
                competing_claims=competing_claims,
            )
        )

    # 3. Calculate KPI summary counts via SQL Aggregation
    kpi_row = session.exec(
        select(
            func.coalesce(func.sum(case((ValidationResult.status == ValidationStatus.open, 1), else_=0)), 0),
            func.coalesce(func.sum(case((ValidationResult.status == ValidationStatus.resolved, 1), else_=0)), 0),
            func.coalesce(func.sum(case((and_(ValidationResult.status == ValidationStatus.open, ValidationResult.validation_type.in_(conflict_val_types)), 1), else_=0)), 0),
            func.coalesce(func.sum(case((and_(ValidationResult.status == ValidationStatus.open, ValidationResult.validation_type.in_(low_conf_types)), 1), else_=0)), 0),
            func.coalesce(func.sum(case((and_(ValidationResult.status == ValidationStatus.open, ValidationResult.validation_type.in_(missing_types)), 1), else_=0)), 0),
        )
    ).first()

    total_open_issues = int(kpi_row[0] or 0)
    resolved_count = int(kpi_row[1] or 0)
    cross_source_conflicts = int(kpi_row[2] or 0)
    low_confidence_issues = int(kpi_row[3] or 0)
    missing_required_attributes = int(kpi_row[4] or 0)
    validation_issues = max(0, total_open_issues - cross_source_conflicts - low_confidence_issues - missing_required_attributes)

    products_needing_review = session.exec(
        select(func.count(distinct(ValidationResult.product_id))).where(ValidationResult.status == ValidationStatus.open)
    ).one() or 0

    summary_counts = ReviewSummaryCountsSchema(
        total_open_issues=total_open_issues,
        total_resolved_issues=resolved_count,
        cross_source_conflicts=cross_source_conflicts,
        low_confidence_issues=low_confidence_issues,
        validation_issues=validation_issues,
        missing_required_attributes=missing_required_attributes,
        products_needing_review=products_needing_review,
    )

    total_pages = max(1, math.ceil(total_items / limit))

    return ReviewsListResponse(
        summary=summary_counts,
        items=review_items,
        total_items=total_items,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Review Item Resolution Endpoint
# ---------------------------------------------------------------------------

class ReviewResolutionRequest(BaseModel):
    action: str  # "accept_current" | "override_custom"
    resolved_value: Optional[Any] = None
    notes: Optional[str] = None


def _get_valid_classpaths() -> set:
    """Returns the set of authoritative taxonomy classpaths from the reference loader."""
    try:
        from app.services.enrichment.reference_loader import get_reference_loader
        loader = get_reference_loader()
        return {t["classpath"] for t in loader.taxonomies}
    except Exception:
        return set()


@router.get("/approved-taxonomies", response_model=List[str], status_code=status.HTTP_200_OK)
def get_approved_taxonomies() -> List[str]:
    """
    Returns the complete list of authoritative, approved taxonomy classpaths for human review.
    """
    classpaths = _get_valid_classpaths()
    return sorted(list(classpaths))


@router.post("/items/{validation_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_review_item(
    validation_id: uuid.UUID,
    request: ReviewResolutionRequest,
    session: Session = Depends(get_session),
):
    """
    Resolve a human review item identified by its ValidationResult ID.

    Accepted actions:
    - accept_current: Mark the current/extracted value as accepted by a human reviewer.
      For taxonomy_unresolved, this is only allowed if the actual_value is a valid taxonomy classpath.
      Otherwise returns HTTP 422 with a clear explanation.
    - override_custom: Apply a human-specified resolved_value.
      For taxonomy_unresolved, the resolved_value must be a valid taxonomy classpath.

    On success:
    - ValidationResult.status is set to "resolved".
    - Associated ProductAttribute (if any) is updated with the resolved value.
    - AuditLog entry is created.
    - Product quality score is recomputed.
    - Product status is transitioned to VERIFIED if all quality gates pass.
    """
    val_record = session.get(ValidationResult, validation_id)
    if not val_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review item with validation_id={validation_id} not found. "
                   f"Ensure the validation_id from the Reviews queue matches an existing ValidationResult record.",
        )

    if val_record.status == ValidationStatus.resolved:
        return {
            "status": "already_resolved",
            "message": "This review item has already been resolved.",
            "validation_id": str(validation_id),
            "product_id": str(val_record.product_id),
        }

    val_type_str = (
        val_record.validation_type.value
        if hasattr(val_record.validation_type, "value")
        else str(val_record.validation_type)
    )

    now = datetime.now(timezone.utc)
    resolved_val: Optional[str] = None
    action = request.action

    # Determine resolution value based on action
    if action == "accept_current":
        current_val = val_record.actual_value
        if current_val is None and val_record.expected_value is not None:
            current_val = val_record.expected_value

        # Taxonomy validation: accept_current for taxonomy_unresolved must be a valid classpath
        if val_type_str == "taxonomy_unresolved":
            valid_classpaths = _get_valid_classpaths()
            current_str = str(current_val) if current_val is not None else ""
            if current_str not in valid_classpaths:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": "taxonomy_value_not_approved",
                        "message": (
                            f"Cannot accept current value '{current_str}' — "
                            f"it is not in the authoritative taxonomy tree. "
                            f"Use 'override_custom' with a valid classpath from the approved taxonomy."
                        ),
                        "valid_classpaths": sorted(valid_classpaths),
                    },
                )

        resolved_val = str(current_val) if current_val is not None else ""

    elif action == "override_custom":
        if request.resolved_value is None or str(request.resolved_value).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="resolved_value is required for override_custom action.",
            )
        resolved_val = str(request.resolved_value).strip()

        # Taxonomy validation: override must be a valid classpath
        if val_type_str == "taxonomy_unresolved":
            valid_classpaths = _get_valid_classpaths()
            if resolved_val not in valid_classpaths:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": "taxonomy_value_not_approved",
                        "message": (
                            f"Override value '{resolved_val}' is not in the authoritative taxonomy tree. "
                            f"Provide an exact classpath from the approved taxonomy."
                        ),
                        "valid_classpaths": sorted(valid_classpaths),
                    },
                )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported action '{action}'. Allowed: 'accept_current', 'override_custom'.",
        )

    # Update associated ProductAttribute if present
    attr: Optional[ProductAttribute] = None
    if val_record.attribute_id:
        attr = session.get(ProductAttribute, val_record.attribute_id)
        if attr and resolved_val:
            attr.raw_value = resolved_val
            attr.normalized_value = resolved_val
            attr.status = AttributeStatus.verified
            attr.updated_at = now
            session.add(attr)

    # Mark validation as resolved
    val_record.status = ValidationStatus.resolved
    val_record.actual_value = resolved_val
    val_record.resolved_at = now
    val_record.resolved_by = "human_reviewer"
    session.add(val_record)

    # Audit log
    audit = AuditLog(
        entity_type="validation_result",
        entity_id=validation_id,
        action="human_review_resolution",
        actor_type="user",
        metadata_json={
            "review_action": action,
            "resolved_value": resolved_val,
            "validation_type": val_type_str,
            "notes": request.notes,
        },
    )
    session.add(audit)

    # Update product taxonomy if resolving a taxonomy issue
    product = session.get(Product, val_record.product_id)
    if product:
        if val_type_str == "taxonomy_unresolved" and resolved_val:
            product.category = resolved_val
            if ">" in resolved_val:
                product.subcategory = resolved_val.split(">")[-1].strip()

        remaining_open = session.exec(
            select(func.count()).select_from(ValidationResult).where(
                ValidationResult.product_id == val_record.product_id,
                ValidationResult.status == ValidationStatus.open,
                ValidationResult.id != validation_id,
            )
        ).one() or 0

        # Recalculate quality: each resolved issue improves score proportionally
        current_score = product.quality_score or 70.0
        if remaining_open == 0:
            product.quality_score = min(99.0, current_score + 15.0)
            product.status = ProductStatus.verified
        else:
            product.quality_score = min(95.0, current_score + 2.0)

        product.updated_at = now
        session.add(product)

    session.commit()

    return {
        "status": "resolved",
        "validation_id": str(validation_id),
        "product_id": str(val_record.product_id),
        "resolved_value": resolved_val,
        "action": action,
        "remaining_open_issues": remaining_open if product else None,
        "product_status": str(
            product.status.value if product and hasattr(product.status, "value") else (str(product.status) if product else "unknown")
        ),
        "product_quality_score": product.quality_score if product else None,
    }

