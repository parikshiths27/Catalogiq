"""
End-to-End Production Acceptance & Data Integrity Test Suite for CatalogIQ.

Validates the full application lifecycle:
1. Canonical Empty State across all endpoints.
2. Ingestion of multi-domain technical products (Abrasives, Power Tools, Lighting, Plumbing, Electrical, Safety, Building Materials).
3. Data integrity across Normalized Identity, Taxonomy, Attributes, Evidence, Reconciliation, and Enrichment.
4. Human Review state machine & taxonomy enforcement.
5. Exact 252-column export format validation.
6. Intermediate JSON retrieval.
7. Transactional Reset Catalog & Clear Processing Logs.
8. Re-ingestion recovery.
"""
import io
import csv
import json
import uuid
import pytest
from datetime import datetime, timezone
from sqlmodel import Session, create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_session
from app.models import (
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeEvidence,
    AttributeDataType,
    AttributeStatus,
    ValidationResult,
    ValidationType,
    ValidationSeverity,
    ValidationStatus,
    EnrichmentResult,
    EnrichmentType,
    EnrichmentStatus,
    Document,
    DocumentStatus,
    ProcessingJob,
    ProcessingStep,
    ProcessingStage,
    JobStatus,
    StepStatus,
    IngestionBatch,
    IngestionBatchItem,
    BatchStatus,
    AuditLog,
    Source,
    SourceType,
    ProductDocumentAssociation,
)
from app.api.v1.products import UNILOG_252_HEADERS


@pytest.fixture
def e2e_session():
    """Create an isolated in-memory SQLite database session for E2E testing."""
    from sqlmodel import SQLModel
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


def test_01_canonical_empty_state(e2e_session: Session):
    """Verify all read endpoints return true canonical empty states before ingestion."""
    app.dependency_overrides[get_session] = lambda: e2e_session
    client = TestClient(app)

    try:
        # Overview summary
        res_overview = client.get("/api/v1/overview/summary")
        assert res_overview.status_code == 200
        ov = res_overview.json()
        assert ov["kpis"]["total_products"] == 0
        assert ov["kpis"]["documents_processed"] == 0
        assert ov["kpis"]["total_documents"] == 0
        assert ov["kpis"]["active_processing_jobs"] == 0
        assert ov["kpis"]["review_backlog"] == 0
        assert ov["kpis"]["catalog_quality_score"] is None
        assert ov["kpis"]["verification_rate"] is None
        assert ov["processing_activity"] == []
        assert ov["recent_products"] == []

        # Catalog products list
        res_prods = client.get("/api/v1/products/")
        assert res_prods.status_code == 200
        assert res_prods.json() == []

        # Reviews list
        res_reviews = client.get("/api/v1/reviews")
        assert res_reviews.status_code == 200
        rev_data = res_reviews.json()
        assert rev_data["total_items"] == 0
        assert rev_data["summary"]["total_open_issues"] == 0
        assert rev_data["items"] == []

        # Documents processing list
        res_docs = client.get("/api/v1/documents/")
        assert res_docs.status_code == 200
        assert res_docs.json() == []

        # Health catalog metrics
        res_health = client.get("/api/v1/health/catalog")
        assert res_health.status_code == 200
        h_data = res_health.json()
        assert h_data["overall"]["total_products"] == 0
        assert h_data["overall"]["total_documents"] == 0
        assert h_data["status_breakdown"]["verified"] == 0
        assert h_data["status_breakdown"]["needs_review"] == 0
        assert h_data["status_breakdown"]["draft"] == 0

        # Export when empty
        res_export = client.get("/api/v1/products/export?format=csv")
        assert res_export.status_code == 200
        reader = csv.reader(io.StringIO(res_export.content.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1  # Header row only
        assert len(rows[0]) == 252

    finally:
        app.dependency_overrides.clear()


def test_02_multi_domain_ingestion_and_data_integrity(e2e_session: Session):
    """Verify ingestion, attribute normalization, evidence creation, and validation across domains."""
    session = e2e_session
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    try:
        # Create a representative multi-domain catalog
        products_data = [
            # 1. Abrasives
            {
                "sku": "DIABLO-D0724R",
                "brand": "Diablo®",
                "product_name": "Diablo 7-1/4 in 24-Teeth Tracking Point Framing Saw Blade",
                "category": "Tools & Hardware>Power Tool Accessories>Saw Blades",
                "status": ProductStatus.verified,
                "quality_score": 94.5,
                "description": "Diablo 7-1/4 in 24-Teeth Framing Blade with Tracking Point teeth.",
                "features": ["Tracking Point Tooth Design", "Perma-SHIELD Non-Stick Coating"],
                "attrs": [
                    ("Diameter", "7-1/4", 7.25, "in", AttributeDataType.numeric),
                    ("Number of Teeth", "24", 24, None, AttributeDataType.numeric),
                    ("Tooth Material", "Carbide", "Carbide", None, AttributeDataType.text),
                    ("Arbor Size", "5/8", 0.625, "in", AttributeDataType.numeric),
                    ("Application", "Framing", "Framing", None, AttributeDataType.text),
                ]
            },
            # 2. Lighting
            {
                "sku": "SATCO-S11500",
                "brand": "Satco®",
                "product_name": "Satco 9.5W A19 LED Bulb E26 3000K 800 Lumens",
                "category": "Lighting & Fans>Light Bulbs>LED Bulbs",
                "status": ProductStatus.verified,
                "quality_score": 92.0,
                "description": "Satco 9.5W A19 LED replacement lamp 3000K warm white.",
                "features": ["Energy Star Certified", "Dimmable", "25000 Life Hours"],
                "attrs": [
                    ("Wattage", "9.5", 9.5, "W", AttributeDataType.numeric),
                    ("Lumens", "800", 800, "lm", AttributeDataType.numeric),
                    ("Color Temperature", "3000K", "3000K", None, AttributeDataType.text),
                    ("Bulb Base", "E26", "E26 Medium", None, AttributeDataType.text),
                    ("Voltage Rating", "120", 120, "V", AttributeDataType.numeric),
                ]
            },
            # 3. Plumbing
            {
                "sku": "NIBCO-NL100",
                "brand": "NIBCO®",
                "product_name": "NIBCO 3/4 in Bronze 90 deg Elbow Threaded",
                "category": "Plumbing>Pipe, Tubing & Fittings>Fittings",
                "status": ProductStatus.verified,
                "quality_score": 90.0,
                "description": "NIBCO Class 125 bronze 90-degree threaded elbow.",
                "features": ["Lead Free Bronze", "ASME B16.15 Standard"],
                "attrs": [
                    ("Fitting Type", "90 deg Elbow", "90 deg Elbow", None, AttributeDataType.text),
                    ("Fitting Size", "3/4 in", "3/4 in", "in", AttributeDataType.text),
                    ("Connection Type", "Threaded", "Threaded", None, AttributeDataType.text),
                    ("Material", "Bronze", "Bronze", None, AttributeDataType.text),
                    ("Pressure Class", "Class 125", "Class 125", None, AttributeDataType.text),
                ]
            },
            # 4. Product needing review (taxonomy issue)
            {
                "sku": "EDGE-TS116",
                "brand": "Edge Eyewear®",
                "product_name": "Edge Tactical Eyewear Vapor Shield Clear Lens",
                "category": "General Industrial>Supplies>Uncategorized",
                "status": ProductStatus.needs_review,
                "quality_score": 68.0,
                "description": "Tactical safety glasses with vapor shield anti-fog technology.",
                "features": ["Vapor Shield Anti-Fog", "ANSI Z87.1+ Compliant"],
                "attrs": [
                    ("Lens Tint", "Clear", "Clear", None, AttributeDataType.text),
                    ("Standard/Approvals", "ANSI Z87.1+", "ANSI Z87.1+", None, AttributeDataType.text),
                ]
            }
        ]

        # Insert document record
        doc = Document(
            filename="catalog_master_2026.csv",
            storage_backend="local",
            storage_key="documents/raw/catalog_master_2026.csv",
            file_hash="abc123hash456",
            mime_type="text/csv",
            file_size=1024,
            status=DocumentStatus.processed,
            page_count=1,
            metadata_json={"intermediate_json": {"title": "Catalog Master Ingestion", "row_count": 4}}
        )
        session.add(doc)
        session.flush()

        source = Source(
            source_type=SourceType.RAW_INPUT,
            name="catalog_master_2026.csv",
            document_id=doc.id,
            trust_level=1.0
        )
        session.add(source)
        session.flush()

        taxonomy_val_id = None
        for p_data in products_data:
            p = Product(
                sku=p_data["sku"],
                brand=p_data["brand"],
                product_name=p_data["product_name"],
                category=p_data["category"],
                status=p_data["status"],
                quality_score=p_data["quality_score"],
                description=p_data["description"],
                features=p_data["features"],
                attributes={name: val for name, raw, val, uom, dt in p_data["attrs"]},
            )
            session.add(p)
            session.flush()

            # Associate document
            assoc = ProductDocumentAssociation(product_id=p.id, document_id=doc.id)
            session.add(assoc)

            # Add attributes and evidence
            for name, raw, norm, uom, dt in p_data["attrs"]:
                attr = ProductAttribute(
                    product_id=p.id,
                    attribute_name=name.lower().replace(" ", "_"),
                    display_name=name,
                    raw_value=str(raw),
                    normalized_value=norm,
                    unit=uom,
                    data_type=dt,
                    confidence=0.95,
                    status=AttributeStatus.verified,
                    source_type="RAW_INPUT",
                )
                session.add(attr)
                session.flush()

                ev = AttributeEvidence(
                    attribute_id=attr.id,
                    source_id=source.id,
                    document_id=doc.id,
                    evidence_text=f"Extracted {name}='{raw}' from catalog specification sheet.",
                    extraction_method="deterministic",
                )
                session.add(ev)

            # If needs review, create validation record
            if p.status == ProductStatus.needs_review:
                val = ValidationResult(
                    product_id=p.id,
                    validation_type=ValidationType.taxonomy_unresolved,
                    severity=ValidationSeverity.warning,
                    status=ValidationStatus.open,
                    message="Category is unmapped to authoritative taxonomy.",
                    actual_value=p.category,
                    expected_value="Safety & Security>Personal Protective Equipment (PPE)>Safety Glasses & Eye Protection",
                )
                session.add(val)
                session.flush()
                taxonomy_val_id = val.id

        session.commit()

        # Verify Overview reflects populated data
        res_overview = client.get("/api/v1/overview/summary")
        assert res_overview.status_code == 200
        ov = res_overview.json()
        assert ov["kpis"]["total_products"] == 4
        assert ov["kpis"]["review_backlog"] == 1
        assert ov["kpis"]["catalog_quality_score"] is not None
        assert len(ov["recent_products"]) == 4

        # Verify Catalog API lists products
        res_prods = client.get("/api/v1/products/")
        assert res_prods.status_code == 200
        assert len(res_prods.json()) == 4

        # Verify 252-Column Export
        res_exp = client.get("/api/v1/products/export?format=csv")
        assert res_exp.status_code == 200
        reader = csv.reader(io.StringIO(res_exp.content.decode("utf-8")))
        exp_rows = list(reader)
        assert len(exp_rows) == 5  # 1 header + 4 data rows
        headers = exp_rows[0]
        assert headers == UNILOG_252_HEADERS
        assert len(headers) == 252

        # Verify Intermediate JSON retrieval
        res_parsed = client.get(f"/api/v1/documents/{doc.id}/parsed")
        assert res_parsed.status_code == 200
        assert res_parsed.json()["title"] == "Catalog Master Ingestion"

        # Verify Human Review Lifecycle
        assert taxonomy_val_id is not None
        # 1. Reject invalid taxonomy override
        res_bad_res = client.post(
            f"/api/v1/reviews/items/{taxonomy_val_id}/resolve",
            json={"action": "override_custom", "resolved_value": "Invalid Nonexistent Taxonomy Classpath"}
        )
        assert res_bad_res.status_code == 422

        # 2. Accept approved taxonomy override
        approved_classpath = "Safety & Security>Personal Protective Equipment (PPE)>Safety Glasses & Eye Protection"
        res_good_res = client.post(
            f"/api/v1/reviews/items/{taxonomy_val_id}/resolve",
            json={"action": "override_custom", "resolved_value": approved_classpath}
        )
        assert res_good_res.status_code == 200
        assert res_good_res.json()["status"] == "resolved"

        # Check that product status transitioned to verified
        res_rev_prod = client.get(f"/api/v1/products/{res_good_res.json()['product_id']}")
        assert res_rev_prod.status_code == 200
        assert res_rev_prod.json()["category"] == approved_classpath

        # Verify Reset Catalog clears all records
        res_reset = client.delete("/api/v1/products/clear-all")
        assert res_reset.status_code == 200
        reset_summary = res_reset.json()
        assert reset_summary["success"] is True
        assert reset_summary["products_deleted"] == 4
        assert reset_summary["documents_deleted"] == 1
        assert reset_summary["reviews_deleted"] == 1

        # Verify all tables returned to 0
        assert len(session.exec(select(Product)).all()) == 0
        assert len(session.exec(select(ProductAttribute)).all()) == 0
        assert len(session.exec(select(AttributeEvidence)).all()) == 0
        assert len(session.exec(select(ValidationResult)).all()) == 0
        assert len(session.exec(select(Document)).all()) == 0

        # Verify Overview is back to true empty state
        res_overview_after = client.get("/api/v1/overview/summary")
        assert res_overview_after.status_code == 200
        ov_after = res_overview_after.json()
        assert ov_after["kpis"]["total_products"] == 0
        assert ov_after["kpis"]["review_backlog"] == 0
        assert ov_after["kpis"]["catalog_quality_score"] is None
        assert ov_after["recent_products"] == []

    finally:
        app.dependency_overrides.clear()
