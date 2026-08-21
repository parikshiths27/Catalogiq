import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select, func
from sqlalchemy import or_, desc

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
    Read-only dashboard overview endpoint providing live database aggregates
    for CatalogIQ operational monitoring.
    """
    # 1. Product aggregates
    total_products = session.exec(select(func.count()).select_from(Product)).one() or 0
    verified_products = session.exec(
        select(func.count()).select_from(Product).where(Product.status == ProductStatus.verified)
    ).one() or 0
    needs_review_products = session.exec(
        select(func.count()).select_from(Product).where(Product.status == ProductStatus.needs_review)
    ).one() or 0
    draft_products = session.exec(
        select(func.count()).select_from(Product).where(Product.status == ProductStatus.draft)
    ).one() or 0

    avg_quality = session.exec(select(func.avg(Product.quality_score)).select_from(Product)).one()
    catalog_quality_score = round(float(avg_quality), 1) if avg_quality is not None and total_products > 0 else None
    verification_rate = round((verified_products / total_products) * 100.0, 1) if total_products > 0 else None

    # 2. Document & Job aggregates
    total_documents = session.exec(select(func.count()).select_from(Document)).one() or 0
    documents_processed = session.exec(
        select(func.count()).select_from(Document).where(Document.status == DocumentStatus.processed)
    ).one() or 0

    # Also count completed IngestionBatches if no documents are recorded as processed
    # (e.g., when ingestion was done via the tabular pipeline which may mark batch but not doc)
    completed_batches = session.exec(
        select(func.count()).select_from(IngestionBatch).where(
            IngestionBatch.status.in_([BatchStatus.completed, BatchStatus.partially_completed])
        )
    ).one() or 0

    # Use the higher of doc-based count vs batch-based count as the authoritative "Sources Processed" metric
    sources_processed = max(documents_processed, completed_batches)
    total_sources = max(total_documents, session.exec(select(func.count()).select_from(IngestionBatch)).one() or 0)

    active_jobs = session.exec(
        select(func.count()).select_from(ProcessingJob).where(
            ProcessingJob.status.in_([JobStatus.queued, JobStatus.processing])
        )
    ).one() or 0

    # 3. Processing Activity List (recent documents joined with job stages)
    recent_docs = session.exec(
        select(Document).order_by(desc(Document.created_at)).limit(10)
    ).all()

    processing_activity: List[ProcessingActivityItemSchema] = []
    for doc in recent_docs:
        # Determine latest job / stage if available
        step_stmt = (
            select(ProcessingStep)
            .where(ProcessingStep.document_id == doc.id)
            .order_by(desc(ProcessingStep.created_at))
        )
        latest_step = session.exec(step_stmt).first()
        stage_str = str(latest_step.stage.value if hasattr(latest_step.stage, "value") else latest_step.stage) if latest_step else doc.status.value if hasattr(doc.status, "value") else str(doc.status)

        processing_activity.append(
            ProcessingActivityItemSchema(
                id=str(doc.id),
                filename=doc.filename,
                status=str(doc.status.value if hasattr(doc.status, "value") else doc.status),
                created_at=doc.created_at,
                page_count=doc.page_count,
                current_stage=stage_str,
            )
        )

    # 4. Review Summary Aggregates
    unresolved_issues = session.exec(
        select(func.count()).select_from(ValidationResult).where(ValidationResult.status == ValidationStatus.open)
    ).one() or 0

    conflict_validation_types = [
        ValidationType.cross_attribute_conflict,
        ValidationType.cross_source_conflict,
        ValidationType.inconsistent_value,
    ]
    val_conflicts = session.exec(
        select(func.count()).select_from(ValidationResult).where(
            ValidationResult.status == ValidationStatus.open,
            ValidationResult.validation_type.in_(conflict_validation_types)
        )
    ).one() or 0

    attr_conflicts = session.exec(
        select(func.count()).select_from(ProductAttribute).where(ProductAttribute.status == AttributeStatus.conflicting)
    ).one() or 0
    total_conflicts = val_conflicts + attr_conflicts

    low_confidence_attrs = session.exec(
        select(func.count()).select_from(ProductAttribute).where(
            or_(
                ProductAttribute.confidence < 0.75,
                ProductAttribute.status == AttributeStatus.needs_review,
                ProductAttribute.status == AttributeStatus.conflicting,
            )
        )
    ).one() or 0

    review_backlog = needs_review_products if needs_review_products > 0 else unresolved_issues

    # 5. Catalog Quality Summary Aggregates
    total_attrs = session.exec(select(func.count()).select_from(ProductAttribute)).one() or 0
    evidence_attrs = session.exec(
        select(func.count(func.distinct(AttributeEvidence.attribute_id))).select_from(AttributeEvidence)
    ).one() or 0

    evidence_coverage_rate = round((evidence_attrs / total_attrs) * 100.0, 1) if total_attrs > 0 else None

    # Completeness rate estimation: % of products with quality score >= 70 or avg product score
    completeness_rate = catalog_quality_score

    products_needing_attention = session.exec(
        select(func.count()).select_from(Product).where(
            or_(
                Product.status == ProductStatus.needs_review,
                Product.quality_score < 70.0
            )
        )
    ).one() or 0

    # 6. Recent Products List
    recent_prods_db = session.exec(
        select(Product).order_by(desc(Product.updated_at)).limit(10)
    ).all()

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
