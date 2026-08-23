import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select, func
from sqlalchemy import or_, desc, case

from app.db.session import get_session
from app.models import (
    Product,
    ProductStatus,
    Document,
    DocumentStatus,
    IngestionBatch,
    BatchStatus,
    ProcessingJob,
    JobStatus,
    ProcessingStep,
    ProductAttribute,
    AttributeStatus,
    AttributeEvidence,
    ValidationResult,
    ValidationStatus,
    ValidationType,
)

router = APIRouter(prefix="/overview")


class OverviewKpisSchema(BaseModel):
    total_products: int
    documents_processed: int
    total_documents: int
    active_processing_jobs: int
    review_backlog: int
    catalog_quality_score: Optional[float] = None
    verification_rate: Optional[float] = None


class ProcessingActivityItemSchema(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime
    page_count: Optional[int] = None
    current_stage: Optional[str] = None


class ReviewSummarySchema(BaseModel):
    unresolved_validation_issues: int
    conflicts_count: int
    low_confidence_attributes: int
    products_needing_review: int


class CatalogQualitySummarySchema(BaseModel):
    overall_quality_score: Optional[float] = None
    completeness_rate: Optional[float] = None
    verified_products_count: int
    needs_review_products_count: int
    draft_products_count: int
    evidence_coverage_rate: Optional[float] = None
    products_needing_attention: int


class RecentProductItemSchema(BaseModel):
    id: str
    product_name: str
    brand: str
    sku: str
    category: str
    status: str
    quality_score: float
    updated_at: datetime


class OverviewSummaryResponse(BaseModel):
    kpis: OverviewKpisSchema
    processing_activity: List[ProcessingActivityItemSchema]
    review_summary: ReviewSummarySchema
    catalog_quality_summary: CatalogQualitySummarySchema
    recent_products: List[RecentProductItemSchema]


@router.get("/summary", response_model=OverviewSummaryResponse, status_code=status.HTTP_200_OK)
def get_overview_summary(session: Session = Depends(get_session)) -> OverviewSummaryResponse:
    """
    High-performance read-only dashboard overview endpoint providing live database aggregates
    for CatalogIQ operational monitoring.
    Consolidates 29+ sequential database queries into 3 optimized queries.
    """
    conflict_validation_types = [
        ValidationType.cross_attribute_conflict,
        ValidationType.cross_source_conflict,
        ValidationType.inconsistent_value,
    ]

    # 1. Single composite query for all scalar aggregate KPIs
    stmt_agg = select(
        select(func.count(Product.id)).scalar_subquery().label("total_products"),
        select(func.count(case((Product.status == ProductStatus.verified, 1)))).scalar_subquery().label("verified_products"),
        select(func.count(case((Product.status == ProductStatus.needs_review, 1)))).scalar_subquery().label("needs_review_products"),
        select(func.count(case((Product.status == ProductStatus.draft, 1)))).scalar_subquery().label("draft_products"),
        select(func.avg(Product.quality_score)).scalar_subquery().label("avg_quality"),
        select(func.count(case((or_(Product.status == ProductStatus.needs_review, Product.quality_score < 70.0), 1)))).scalar_subquery().label("products_needing_attention"),
        select(func.count(Document.id)).scalar_subquery().label("total_documents"),
        select(func.count(case((Document.status == DocumentStatus.processed, 1)))).scalar_subquery().label("documents_processed"),
        select(func.count(IngestionBatch.id)).scalar_subquery().label("total_batches"),
        select(func.count(case((IngestionBatch.status.in_([BatchStatus.completed, BatchStatus.partially_completed]), 1)))).scalar_subquery().label("completed_batches"),
        select(func.count(case((ProcessingJob.status.in_([JobStatus.queued, JobStatus.processing]), 1)))).scalar_subquery().label("active_jobs"),
        select(func.count(case((ValidationResult.status == ValidationStatus.open, 1)))).scalar_subquery().label("unresolved_issues"),
        select(func.count(case(((ValidationResult.status == ValidationStatus.open) & ValidationResult.validation_type.in_(conflict_validation_types), 1)))).scalar_subquery().label("val_conflicts"),
        select(func.count(case((ProductAttribute.status == AttributeStatus.conflicting, 1)))).scalar_subquery().label("attr_conflicts"),
        select(func.count(case((or_(ProductAttribute.confidence < 0.75, ProductAttribute.status.in_([AttributeStatus.needs_review, AttributeStatus.conflicting])), 1)))).scalar_subquery().label("low_confidence_attrs"),
        select(func.count(ProductAttribute.id)).scalar_subquery().label("total_attrs"),
        select(func.count(func.distinct(AttributeEvidence.attribute_id))).scalar_subquery().label("evidence_attrs"),
    )

    # 2. Correlated query for recent documents with latest stage
    latest_stage_subq = (
        select(ProcessingStep.stage)
        .where(ProcessingStep.document_id == Document.id)
        .order_by(desc(ProcessingStep.created_at))
        .limit(1)
        .correlate(Document)
        .scalar_subquery()
    )

    doc_stmt = (
        select(
            Document.id,
            Document.filename,
            Document.status,
            Document.created_at,
            Document.page_count,
            latest_stage_subq.label("latest_stage"),
        )
        .order_by(desc(Document.created_at))
        .limit(10)
    )

    # 3. Recent Products
    prod_stmt = select(Product).order_by(desc(Product.updated_at)).limit(10)

    # Execute the 3 consolidated queries
    row = session.exec(stmt_agg).first()
    recent_doc_rows = session.exec(doc_stmt).all()
    recent_prods_db = session.exec(prod_stmt).all()

    total_products = (row[0] if row else 0) or 0
    verified_products = (row[1] if row else 0) or 0
    needs_review_products = (row[2] if row else 0) or 0
    draft_products = (row[3] if row else 0) or 0
    avg_quality = row[4] if row else None
    products_needing_attention = (row[5] if row else 0) or 0

    total_documents = (row[6] if row else 0) or 0
    documents_processed = (row[7] if row else 0) or 0
    total_batches = (row[8] if row else 0) or 0
    completed_batches = (row[9] if row else 0) or 0
    active_jobs = (row[10] if row else 0) or 0

    unresolved_issues = (row[11] if row else 0) or 0
    val_conflicts = (row[12] if row else 0) or 0
    attr_conflicts = (row[13] if row else 0) or 0
    total_conflicts = val_conflicts + attr_conflicts
    low_confidence_attrs = (row[14] if row else 0) or 0
    total_attrs = (row[15] if row else 0) or 0
    evidence_attrs = (row[16] if row else 0) or 0

    # Derived KPIs with safe defaults
    catalog_quality_score = round(float(avg_quality), 1) if avg_quality is not None and total_products > 0 else None
    verification_rate = round((verified_products / total_products) * 100.0, 1) if total_products > 0 else None
    sources_processed = max(documents_processed, completed_batches)
    total_sources = max(total_documents, total_batches)
    review_backlog = (needs_review_products if needs_review_products > 0 else unresolved_issues) if total_products > 0 else 0
    evidence_coverage_rate = round((evidence_attrs / total_attrs) * 100.0, 1) if (total_attrs > 0 and total_products > 0) else None
    completeness_rate = catalog_quality_score

    processing_activity: List[ProcessingActivityItemSchema] = [
        ProcessingActivityItemSchema(
            id=str(r[0]),
            filename=r[1],
            status=str(r[2].value if hasattr(r[2], "value") else r[2]),
            created_at=r[3],
            page_count=r[4],
            current_stage=str(r[5].value if hasattr(r[5], "value") else r[5]) if r[5] else str(r[2].value if hasattr(r[2], "value") else r[2]),
        )
        for r in recent_doc_rows
    ]

    recent_products: List[RecentProductItemSchema] = [
        RecentProductItemSchema(
            id=str(p.id),
            product_name=p.product_name,
            brand=p.brand,
            sku=p.sku,
            category=p.category,
            status=str(p.status.value if hasattr(p.status, "value") else p.status),
            quality_score=p.quality_score,
            updated_at=p.updated_at,
        )
        for p in recent_prods_db
    ]

    return OverviewSummaryResponse(
        kpis=OverviewKpisSchema(
            total_products=total_products,
            documents_processed=sources_processed,
            total_documents=total_sources,
            active_processing_jobs=active_jobs,
            review_backlog=review_backlog,
            catalog_quality_score=catalog_quality_score,
            verification_rate=verification_rate,
        ),
        processing_activity=processing_activity,
        review_summary=ReviewSummarySchema(
            unresolved_validation_issues=unresolved_issues,
            conflicts_count=total_conflicts,
            low_confidence_attributes=low_confidence_attrs,
            products_needing_review=needs_review_products,
        ),
        catalog_quality_summary=CatalogQualitySummarySchema(
            overall_quality_score=catalog_quality_score,
            completeness_rate=completeness_rate,
            verified_products_count=verified_products,
            needs_review_products_count=needs_review_products,
            draft_products_count=draft_products,
            evidence_coverage_rate=evidence_coverage_rate,
            products_needing_attention=products_needing_attention,
        ),
        recent_products=recent_products,
    )
