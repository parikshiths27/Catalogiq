import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlmodel import Session, select, func
import pytest

from app.main import app
from app.db.session import get_session
from app.models import (
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeDataType,
    AttributeStatus,
    ValidationResult,
    ValidationType,
    ValidationSeverity,
    ValidationStatus,
    AttributeEvidence,
    Source,
    SourceType,
    Document,
    DocumentStatus,
    AuditLog,
)

client = TestClient(app)


def test_catalog_health_empty_db(session: Session):
    """
    1, 19. Verifies /api/v1/health/catalog returns clean 0/0.0 defaults without division-by-zero or NaN when DB is empty.
    """
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        response = client.get("/api/v1/health/catalog")
        assert response.status_code == 200
        data = response.json()

        # Overall
        assert data["overall"]["quality_score"] is None
        assert data["overall"]["completeness_rate"] is None
        assert data["overall"]["verification_rate"] is None
        assert data["overall"]["evidence_coverage"] is None
        assert data["overall"]["total_products"] == 0
        assert data["overall"]["total_attributes"] == 0
        assert data["overall"]["total_documents"] == 0

        # Status breakdown
        assert data["status_breakdown"]["verified"] == 0
        assert data["status_breakdown"]["needs_review"] == 0
        assert data["status_breakdown"]["draft"] == 0

        # Issues
        assert data["issues"]["total_open_issues"] == 0
        assert data["issues"]["cross_source_conflicts"] == 0
        assert data["issues"]["low_confidence_attributes"] == 0
        assert data["issues"]["validation_issues"] == 0
        assert data["issues"]["missing_required_attributes"] == 0

        # Collections
        assert data["category_health"] == []
        assert data["brand_health"] == []
        assert data["products_needing_attention"] == []
        assert data["worst_products"] == []
    finally:
        app.dependency_overrides.clear()


def test_catalog_health_single_healthy_product(session: Session):
    """
    2, 4, 5, 6, 7. Verifies single verified product health calculations.
    """
    prod = Product(
        sku="P-HEALTHY-100",
        brand="Siemens",
        product_name="Healthy Motor 100",
        category="Motors",
        status=ProductStatus.verified,
        quality_score=95.0,
    )
    session.add(prod)
    session.commit()
    session.refresh(prod)

    attr = ProductAttribute(
        product_id=prod.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="15 kW",
        unit="kW",
        data_type=AttributeDataType.numeric,
        confidence=0.95,
        status=AttributeStatus.verified,
        source_type="document",
    )
    session.add(attr)
    session.commit()
    session.refresh(attr)

    ev = AttributeEvidence(
        attribute_id=attr.id,
        evidence_text="15 kW rated output",
    )
    session.add(ev)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        res = client.get("/api/v1/health/catalog")
        assert res.status_code == 200
        data = res.json()

        assert data["overall"]["total_products"] == 1
        assert data["overall"]["quality_score"] == 95.0
        assert data["overall"]["verification_rate"] == 100.0
        assert data["overall"]["evidence_coverage"] == 100.0
        assert data["status_breakdown"]["verified"] == 1
        assert data["status_breakdown"]["needs_review"] == 0
        assert data["status_breakdown"]["draft"] == 0
        assert data["issues"]["total_open_issues"] == 0
    finally:
        app.dependency_overrides.clear()


def test_catalog_health_mixed_catalog_and_aggregates(session: Session):
    """
    3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18. Verifies mixed catalog metrics,
    category/brand grouping, attention queue, worst products, limits, and read-only guarantee.
    """
    # 1. Product 1 (Verified, Siemens, Motors, quality 90.0)
    p1 = Product(
        sku="P-MTR-01", brand="Siemens", product_name="Siemens Motor 10kW", category="Motors", status=ProductStatus.verified, quality_score=90.0
    )
    # 2. Product 2 (Needs Review, Siemens, Motors, quality 50.0, conflict)
    p2 = Product(
        sku="P-MTR-02", brand="Siemens", product_name="Siemens Motor 20kW", category="Motors", status=ProductStatus.needs_review, quality_score=50.0
    )
    # 3. Product 3 (Draft, ABB, Drives, quality 40.0, missing required)
    p3 = Product(
        sku="P-DRV-01", brand="ABB", product_name="ABB Drive 100A", category="Drives", status=ProductStatus.draft, quality_score=40.0
    )

    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()
    session.refresh(p1)
    session.refresh(p2)
    session.refresh(p3)

    # Attributes
    a1 = ProductAttribute(product_id=p1.id, attribute_name="rated_power", display_name="Rated Power", raw_value="10 kW", confidence=0.95, status=AttributeStatus.verified, data_type=AttributeDataType.numeric, source_type="document")
    a2 = ProductAttribute(product_id=p2.id, attribute_name="rated_power", display_name="Rated Power", raw_value="20 kW", confidence=0.60, status=AttributeStatus.conflicting, data_type=AttributeDataType.numeric, source_type="document")
    a3 = ProductAttribute(product_id=p3.id, attribute_name="current", display_name="Current", raw_value="100 A", confidence=0.50, status=AttributeStatus.needs_review, data_type=AttributeDataType.numeric, source_type="document")

    session.add(a1)
    session.add(a2)
    session.add(a3)
    session.commit()
    session.refresh(a1)
    session.refresh(a2)
    session.refresh(a3)

    # Evidence for p1 attribute
    ev1 = AttributeEvidence(attribute_id=a1.id, evidence_text="10 kW power spec")
    session.add(ev1)

    # Validation results
    val_conflict = ValidationResult(
        product_id=p2.id,
        attribute_id=a2.id,
        validation_type=ValidationType.cross_source_conflict,
        severity=ValidationSeverity.error,
        status=ValidationStatus.open,
        message="Cross-source conflict on power rating",
    )
    val_missing = ValidationResult(
        product_id=p3.id,
        validation_type=ValidationType.missing_required_attribute,
        severity=ValidationSeverity.error,
        status=ValidationStatus.open,
        message="Required attribute voltage is missing",
    )
    session.add(val_conflict)
    session.add(val_missing)
    session.commit()

    # Pre-test record count snapshot for Read-Only verification
    prod_count_before = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_before = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    val_count_before = session.exec(select(func.count()).select_from(ValidationResult)).one()
    audit_count_before = session.exec(select(func.count()).select_from(AuditLog)).one()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        res = client.get("/api/v1/health/catalog")
        assert res.status_code == 200
        data = res.json()

        # Overall Quality Average: (90.0 + 50.0 + 40.0) / 3 = 60.0
        assert data["overall"]["total_products"] == 3
        assert data["overall"]["quality_score"] == 60.0
        assert data["overall"]["verification_rate"] == 33.3
        assert data["overall"]["evidence_coverage"] == 33.3  # 1 distinct evidence attribute out of 3 total attributes

        # Status breakdown
        assert data["status_breakdown"]["verified"] == 1
        assert data["status_breakdown"]["needs_review"] == 1
        assert data["status_breakdown"]["draft"] == 1

        # Issues
        assert data["issues"]["total_open_issues"] == 2
        assert data["issues"]["cross_source_conflicts"] >= 1  # val_conflict + attr conflict
        assert data["issues"]["missing_required_attributes"] == 1

        # Category Health Grouping
        cat_health = {c["category"]: c for c in data["category_health"]}
        assert "Motors" in cat_health
        assert cat_health["Motors"]["product_count"] == 2
        assert cat_health["Motors"]["avg_quality_score"] == 70.0  # (90 + 50) / 2
        assert cat_health["Motors"]["verification_rate"] == 50.0

        assert "Drives" in cat_health
        assert cat_health["Drives"]["product_count"] == 1
        assert cat_health["Drives"]["avg_quality_score"] == 40.0

        # Brand Health Grouping
        brand_health = {b["brand"]: b for b in data["brand_health"]}
        assert "Siemens" in brand_health
        assert brand_health["Siemens"]["product_count"] == 2
        assert brand_health["Siemens"]["avg_quality_score"] == 70.0

        assert "ABB" in brand_health
        assert brand_health["ABB"]["product_count"] == 1

        # Worst Products Ranking (quality_score ASC: p3 (40.0), p2 (50.0), p1 (90.0))
        worst = data["worst_products"]
        assert len(worst) <= 10
        assert worst[0]["id"] == str(p3.id)
        assert worst[0]["quality_score"] == 40.0
        assert worst[1]["id"] == str(p2.id)

        # Products Needing Attention (P2 needs_review / conflict prioritized)
        attention = data["products_needing_attention"]
        assert len(attention) <= 10
        assert attention[0]["id"] == str(p2.id)
        assert attention[0]["status"] == "needs_review"
        assert attention[0]["has_conflicts"] is True

        # 18. READ-ONLY GUARANTEE VERIFICATION
        prod_count_after = session.exec(select(func.count()).select_from(Product)).one()
        attr_count_after = session.exec(select(func.count()).select_from(ProductAttribute)).one()
        val_count_after = session.exec(select(func.count()).select_from(ValidationResult)).one()
        audit_count_after = session.exec(select(func.count()).select_from(AuditLog)).one()

        assert prod_count_before == prod_count_after
        assert attr_count_before == attr_count_after
        assert val_count_before == val_count_after
        assert audit_count_before == audit_count_after

    finally:
        app.dependency_overrides.clear()
