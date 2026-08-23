import uuid
from fastapi.testclient import TestClient
from sqlmodel import Session, select
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


def test_reviews_empty_db(session: Session):
    """
    Verifies /api/v1/reviews returns clean empty response when no products/issues exist.
    """
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        response = client.get("/api/v1/reviews")
        assert response.status_code == 200
        data = response.json()

        assert "summary" in data
        assert data["summary"]["total_open_issues"] == 0
        assert data["summary"]["cross_source_conflicts"] == 0
        assert data["summary"]["low_confidence_issues"] == 0
        assert data["summary"]["validation_issues"] == 0
        assert data["summary"]["missing_required_attributes"] == 0
        assert data["items"] == []
        assert data["total_items"] == 0
    finally:
        app.dependency_overrides.clear()


def test_reviews_populated_conflicts_and_provenance(session: Session):
    """
    Verifies /api/v1/reviews returns open issues, cross-source conflict classification,
    competing claims, evidence quotes, and filtering capabilities.
    """
    # 1. Create product & attributes
    prod = Product(
        sku="P-MOTOR-500",
        brand="Siemens",
        product_name="Siemens Industrial Motor 11kW",
        category="Motors",
        status=ProductStatus.needs_review,
        quality_score=65.0,
    )
    session.add(prod)
    session.commit()
    session.refresh(prod)

    attr = ProductAttribute(
        product_id=prod.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="11 kW",
        unit="kW",
        data_type=AttributeDataType.numeric,
        confidence=0.66,
        status=AttributeStatus.conflicting,
        source_type="document",
    )
    session.add(attr)
    session.commit()
    session.refresh(attr)

    # 2. Create document & evidence
    doc = Document(
        filename="siemens_catalog_2026.pdf",
        storage_backend="local",
        storage_key="docs/siemens.pdf",
        file_hash="hash123",
        mime_type="application/pdf",
        file_size=2048,
        page_count=12,
        status=DocumentStatus.processed,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    src_a = Source(
        name="Siemens Official Catalog PDF",
        source_type=SourceType.document,
        trust_level=0.95,
        document_id=doc.id,
    )
    src_b = Source(
        name="Distributor Catalog Sheet",
        source_type=SourceType.document,
        trust_level=0.70,
    )
    session.add(src_a)
    session.add(src_b)
    session.commit()
    session.refresh(src_a)
    session.refresh(src_b)

    ev = AttributeEvidence(
        attribute_id=attr.id,
        source_id=src_a.id,
        document_id=doc.id,
        page_number=5,
        evidence_text="Motor rated power output is 11 kW at 400V 50Hz.",
        extraction_method="llm",
    )
    session.add(ev)

    # 3. Create ValidationResult conflict using reconciler structure (expected_value=winning_claim dict, actual_value=competing_claims list)
    winning_claim_dict = {
        "source_id": str(src_a.id),
        "source_name": src_a.name,
        "raw_value": "11 kW",
        "trust_level": 0.95,
    }
    competing_claim_dict = {
        "source_id": str(src_b.id),
        "source_name": src_b.name,
        "raw_value": "7.5 kW",
        "trust_level": 0.70,
    }

    val_conflict = ValidationResult(
        product_id=prod.id,
        attribute_id=attr.id,
        validation_type=ValidationType.cross_source_conflict,
        severity=ValidationSeverity.error,
        status=ValidationStatus.open,
        message="Cross-source conflict: Manufacturer PDF claims 11 kW vs Distributor Catalog claims 7.5 kW",
        expected_value=winning_claim_dict,
        actual_value=[competing_claim_dict],
    )
    session.add(val_conflict)
    session.commit()
    session.refresh(val_conflict)

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # GET /api/v1/reviews
        res = client.get("/api/v1/reviews")
        assert res.status_code == 200
        data = res.json()

        assert data["summary"]["total_open_issues"] == 1
        assert data["summary"]["cross_source_conflicts"] == 1
        assert data["total_items"] == 1

        item = data["items"][0]
        assert item["validation_id"] == str(val_conflict.id)
        assert item["product_name"] == "Siemens Industrial Motor 11kW"
        assert item["brand"] == "Siemens"
        assert item["sku"] == "P-MOTOR-500"
        assert item["display_name"] == "Rated Power"
        assert item["category_type"] == "cross_source_conflict"

        # Evidence checks
        assert len(item["evidence"]) == 1
        assert item["evidence"][0]["document_filename"] == "siemens_catalog_2026.pdf"
        assert item["evidence"][0]["page_number"] == 5
        assert "11 kW at 400V" in item["evidence"][0]["evidence_text"]

        # A. Test accept_source_a: selects winning claim 11 kW & source_id provenance
        res_resolve = client.post(
            f"/api/v1/products/{prod.id}/validation/{val_conflict.id}/resolve",
            json={
                "resolution": "accept_source_a",
                "resolved_value": "11 kW",
                "notes": "Accepted 11 kW based on official manufacturer PDF datasheet",
            },
        )
        assert res_resolve.status_code == 200
        resolve_data = res_resolve.json()
        assert resolve_data["status"] == "resolved"

        # Verify target attribute raw_value updated and status set to AttributeStatus.verified
        session.refresh(attr)
        assert attr.raw_value == "11 kW"
        assert attr.status == AttributeStatus.verified

        # Verify audit log recorded selected_source_id
        audit_stmt = select(AuditLog).where(AuditLog.entity_id == val_conflict.id)
        audits = session.exec(audit_stmt).all()
        assert len(audits) == 1
        assert audits[0].metadata_json["resolution"] == "accept_source_a"
        assert audits[0].metadata_json["resolved_value"] == "11 kW"
        assert audits[0].metadata_json["selected_source_id"] == str(src_a.id)

        # D. Verify evidence and sources are preserved
        ev_after = session.get(AttributeEvidence, ev.id)
        assert ev_after is not None
        assert ev_after.evidence_text == "Motor rated power output is 11 kW at 400V 50Hz."
        assert session.get(Source, src_a.id) is not None
        assert session.get(Source, src_b.id) is not None

        # H. Test Idempotency: submitting exact same resolution again returns already_resolved without creating second audit log
        res_idempotent = client.post(
            f"/api/v1/products/{prod.id}/validation/{val_conflict.id}/resolve",
            json={
                "resolution": "accept_source_a",
                "resolved_value": "11 kW",
                "notes": "Accepted 11 kW based on official manufacturer PDF datasheet",
            },
        )
        assert res_idempotent.status_code == 200
        assert res_idempotent.json()["status"] == "already_resolved"

        audits_after_repeat = session.exec(audit_stmt).all()
        assert len(audits_after_repeat) == 1  # Exactly 1 audit log created

        # I. Test Conflicting decision: attempting to change resolution to accept_source_b returns HTTP 409
        res_conflict = client.post(
            f"/api/v1/products/{prod.id}/validation/{val_conflict.id}/resolve",
            json={
                "resolution": "accept_source_b",
                "resolved_value": "7.5 kW",
            },
        )
        assert res_conflict.status_code == 409
        assert "already resolved with 'accept_source_a'" in res_conflict.json()["detail"]

    finally:
        app.dependency_overrides.clear()


def test_reviews_resolution_accept_source_b(session: Session):
    """
    Verifies accept_source_b resolution on a genuine cross-source conflict:
    Source A (Manufacturer PDF: 11 kW) vs Source B (Distributor: 7.5 kW).
    Submitting accept_source_b must select 7.5 kW, set status to verified,
    mark ValidationResult as resolved, and record Source B's source_id in AuditLog.
    """
    # 1. Create product & attribute
    prod = Product(
        sku="P-MOTOR-750",
        brand="ABB",
        product_name="ABB Motor 7.5kW",
        category="Motors",
        status=ProductStatus.needs_review,
        quality_score=60.0,
    )
    unrelated_prod = Product(
        sku="P-UNRELATED-999",
        brand="UnrelatedBrand",
        product_name="Unrelated Product",
        category="Sensors",
        status=ProductStatus.verified,
        quality_score=95.0,
    )
    session.add(prod)
    session.add(unrelated_prod)
    session.commit()
    session.refresh(prod)
    session.refresh(unrelated_prod)

    attr = ProductAttribute(
        product_id=prod.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="11 kW",
        unit="kW",
        data_type=AttributeDataType.numeric,
        confidence=0.60,
        status=AttributeStatus.conflicting,
        source_type="document",
    )
    unrelated_attr = ProductAttribute(
        product_id=unrelated_prod.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="15 kW",
        unit="kW",
        data_type=AttributeDataType.numeric,
        confidence=0.99,
        status=AttributeStatus.verified,
        source_type="document",
    )
    session.add(attr)
    session.add(unrelated_attr)
    session.commit()
    session.refresh(attr)
    session.refresh(unrelated_attr)

    # 2. Create Sources & Evidence
    src_a = Source(name="Manufacturer Spec Sheet", source_type=SourceType.document, trust_level=0.90)
    src_b = Source(name="Distributor Catalog Sheet", source_type=SourceType.catalog, trust_level=0.75)
    session.add(src_a)
    session.add(src_b)
    session.commit()
    session.refresh(src_a)
    session.refresh(src_b)

    ev_a = AttributeEvidence(attribute_id=attr.id, source_id=src_a.id, evidence_text="Manufacturer claims 11 kW")
    ev_b = AttributeEvidence(attribute_id=attr.id, source_id=src_b.id, evidence_text="Distributor claims 7.5 kW")
    session.add(ev_a)
    session.add(ev_b)
    session.commit()

    # 3. Create ValidationResult for cross-source conflict
    val_conflict = ValidationResult(
        product_id=prod.id,
        attribute_id=attr.id,
        validation_type=ValidationType.cross_source_conflict,
        severity=ValidationSeverity.error,
        status=ValidationStatus.open,
        message="Cross-source conflict: Manufacturer claims 11 kW vs Distributor claims 7.5 kW",
        expected_value={
            "source_id": str(src_a.id),
            "source_name": src_a.name,
            "raw_value": "11 kW",
            "trust_level": 0.90,
        },
        actual_value=[
            {
                "source_id": str(src_b.id),
                "source_name": src_b.name,
                "raw_value": "7.5 kW",
                "trust_level": 0.75,
            }
        ],
    )
    session.add(val_conflict)
    session.commit()
    session.refresh(val_conflict)

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # Submit accept_source_b resolution
        res = client.post(
            f"/api/v1/products/{prod.id}/validation/{val_conflict.id}/resolve",
            json={"resolution": "accept_source_b", "notes": "Accepted Distributor claim 7.5 kW after review"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "resolved"

        # Verify ProductAttribute.raw_value == "7.5 kW" and status == AttributeStatus.verified
        session.refresh(attr)
        assert attr.raw_value == "7.5 kW"
        assert attr.status == AttributeStatus.verified

        # Verify ValidationResult.status == ValidationStatus.resolved
        session.refresh(val_conflict)
        assert val_conflict.status == ValidationStatus.resolved

        # Verify AuditLog metadata_json records selected_source_id == src_b.id
        audit_stmt = select(AuditLog).where(AuditLog.entity_id == val_conflict.id)
        audit = session.exec(audit_stmt).first()
        assert audit is not None
        assert audit.metadata_json["resolution"] == "accept_source_b"
        assert audit.metadata_json["resolved_value"] == "7.5 kW"
        assert audit.metadata_json["selected_source_id"] == str(src_b.id)

        # Verify ALL AttributeEvidence records remain intact
        assert session.get(AttributeEvidence, ev_a.id) is not None
        assert session.get(AttributeEvidence, ev_b.id) is not None

        # Verify both Source records remain intact
        assert session.get(Source, src_a.id) is not None
        assert session.get(Source, src_b.id) is not None

        # Verify unrelated products/attributes remain unchanged
        session.refresh(unrelated_prod)
        session.refresh(unrelated_attr)
        assert unrelated_attr.raw_value == "15 kW"
        assert unrelated_attr.status == AttributeStatus.verified
        assert unrelated_prod.quality_score == 95.0
        assert unrelated_prod.status == ProductStatus.verified

    finally:
        app.dependency_overrides.clear()


def test_reviews_resolution_scoping_and_custom_value(session: Session):
    """
    Verifies custom_value resolution, isolation of unrelated products/attributes,
    and rejection of cross-product validation mismatches.
    """
    # Create product 1 and product 2
    p1 = Product(
        sku="SKU-AAA", brand="BrandA", product_name="Product A", category="CatA", status=ProductStatus.needs_review, quality_score=60.0
    )
    p2 = Product(
        sku="SKU-BBB", brand="BrandB", product_name="Product B", category="CatB", status=ProductStatus.verified, quality_score=90.0
    )
    session.add(p1)
    session.add(p2)
    session.commit()
    session.refresh(p1)
    session.refresh(p2)

    attr1 = ProductAttribute(
        product_id=p1.id, attribute_name="voltage", display_name="Voltage", raw_value="220V", unit="V", data_type=AttributeDataType.numeric, confidence=0.8, status=AttributeStatus.needs_review, source_type="doc"
    )
    attr2 = ProductAttribute(
        product_id=p2.id, attribute_name="voltage", display_name="Voltage", raw_value="400V", unit="V", data_type=AttributeDataType.numeric, confidence=0.99, status=AttributeStatus.verified, source_type="doc"
    )
    session.add(attr1)
    session.add(attr2)
    session.commit()
    session.refresh(attr1)
    session.refresh(attr2)

    val1 = ValidationResult(
        product_id=p1.id, attribute_id=attr1.id, validation_type=ValidationType.invalid_unit, severity=ValidationSeverity.warning, status=ValidationStatus.open, message="Invalid unit specified"
    )
    session.add(val1)
    session.commit()
    session.refresh(val1)

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # J. Scoping check: Attempting to resolve val1 under p2's URL should return 400 Bad Request
        res_mismatch = client.post(
            f"/api/v1/products/{p2.id}/validation/{val1.id}/resolve",
            json={"resolution": "custom_value", "resolved_value": "230 V"},
        )
        assert res_mismatch.status_code == 400
        assert "does not belong to product" in res_mismatch.json()["detail"]

        # C. Resolve val1 under p1 with custom_value
        res_custom = client.post(
            f"/api/v1/products/{p1.id}/validation/{val1.id}/resolve",
            json={"resolution": "custom_value", "resolved_value": "230 V", "notes": "Verified custom voltage"},
        )
        assert res_custom.status_code == 200
        assert res_custom.json()["status"] == "resolved"

        # Verify attr1 updated, attr2 untouched
        session.refresh(attr1)
        session.refresh(attr2)
        assert attr1.raw_value == "230 V"
        assert attr1.status == AttributeStatus.verified
        assert attr2.raw_value == "400V"  # Unrelated attribute untouched!
        assert attr2.status == AttributeStatus.verified

        # G. Verify p2 quality score and status remain completely untouched
        session.refresh(p2)
        assert p2.quality_score == 90.0
        assert p2.status == ProductStatus.verified
    finally:
        app.dependency_overrides.clear()


def test_taxonomy_unresolved_human_review_resolution(session: Session):
    """
    Verifies that an invalid current taxonomy classpath cannot be accepted via accept_current,
    cannot be overridden with another invalid value, but CAN be successfully replaced with
    an approved classpath from the authoritative taxonomy tree via override_custom.
    Also verifies Product category/subcategory update, quality score recalculation,
    ValidationResult status transition, and AuditLog recording.
    """
    from app.api.v1.reviews import _get_valid_classpaths
    valid_classpaths = _get_valid_classpaths()
    assert len(valid_classpaths) > 0, "Reference loader must provide approved taxonomies"
    approved_classpath = sorted(list(valid_classpaths))[0]  # Take a valid approved classpath

    # 1. Create a product with an unapproved/invalid taxonomy value
    invalid_extracted_category = "Industrial Supplies & MRO>General Supplies>Miscellaneous"
    prod = Product(
        sku="TEST-SKU-TAXONOMY-001",
        brand="TestBrand",
        product_name="Industrial Valve Assembly",
        category=invalid_extracted_category,
        subcategory="Miscellaneous",
        status=ProductStatus.needs_review,
        quality_score=60.0,
    )
    session.add(prod)
    session.commit()
    session.refresh(prod)

    # 2. Create ValidationResult for taxonomy_unresolved
    val = ValidationResult(
        product_id=prod.id,
        validation_type=ValidationType.taxonomy_unresolved,
        severity=ValidationSeverity.warning,
        status=ValidationStatus.open,
        message=f"Category '{invalid_extracted_category}' is not in authoritative taxonomy tree",
        actual_value=invalid_extracted_category,
    )
    session.add(val)
    session.commit()
    session.refresh(val)

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # A. Fetch approved taxonomies endpoint
        res_tax = client.get("/api/v1/reviews/approved-taxonomies")
        assert res_tax.status_code == 200
        tax_list = res_tax.json()
        assert approved_classpath in tax_list

        # B. Attempt accept_current with invalid value -> must be rejected with 422
        res_accept = client.post(
            f"/api/v1/reviews/items/{val.id}/resolve",
            json={"action": "accept_current"},
        )
        assert res_accept.status_code == 422
        assert "taxonomy_value_not_approved" in str(res_accept.json())

        # C. Attempt override_custom with another invalid value -> must be rejected with 422
        res_invalid_override = client.post(
            f"/api/v1/reviews/items/{val.id}/resolve",
            json={
                "action": "override_custom",
                "resolved_value": "TotallyFakeCategory>Subcategory>Leaf",
            },
        )
        assert res_invalid_override.status_code == 422
        assert "taxonomy_value_not_approved" in str(res_invalid_override.json())

        # D. Override with valid approved classpath -> must succeed with 200
        res_valid = client.post(
            f"/api/v1/reviews/items/{val.id}/resolve",
            json={
                "action": "override_custom",
                "resolved_value": approved_classpath,
                "notes": "Mapped to approved canonical taxonomy classpath via human review UI",
            },
        )
        assert res_valid.status_code == 200
        res_data = res_valid.json()
        assert res_data["status"] == "resolved"
        assert res_data["resolved_value"] == approved_classpath
        assert res_data["product_status"] == "verified"

        # E. Verify ValidationResult updated in DB
        session.refresh(val)
        assert val.status == ValidationStatus.resolved
        assert val.actual_value == approved_classpath
        assert val.resolved_by == "human_reviewer"
        assert val.resolved_at is not None

        # F. Verify Product updated in DB
        session.refresh(prod)
        assert prod.category == approved_classpath
        if ">" in approved_classpath:
            assert prod.subcategory == approved_classpath.split(">")[-1].strip()
        assert prod.status == ProductStatus.verified
        assert prod.quality_score > 60.0

        # G. Verify AuditLog recorded
        audit = session.exec(
            select(AuditLog).where(
                AuditLog.entity_type == "validation_result",
                AuditLog.entity_id == val.id,
            )
        ).first()
        assert audit is not None
        assert audit.action == "human_review_resolution"
        assert audit.metadata_json["resolved_value"] == approved_classpath

        # H. Verify issue moves from open to resolved in reviews queue
        res_open = client.get("/api/v1/reviews?status=open")
        open_ids = [item["validation_id"] for item in res_open.json()["items"]]
        assert str(val.id) not in open_ids

        res_resolved = client.get("/api/v1/reviews?status=resolved")
        resolved_ids = [item["validation_id"] for item in res_resolved.json()["items"]]
        assert str(val.id) in resolved_ids

    finally:
        app.dependency_overrides.clear()

