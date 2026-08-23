import uuid
import pytest
from datetime import datetime, timezone
from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.exc import IntegrityError
from app.models import (
    Product, ProductAttribute, AttributeEvidence, Source, Document, 
    ProductVersion, CacheEntry, DuplicateCandidate, AuditLog,
    AttributeDataType, AttributeStatus, SourceType, CacheType, CacheStatus,
    DuplicateMethod, DuplicateStatus, ActorType
)
from app.services import CacheService, ProductService, DuplicateService


def test_product_attribute_uniqueness_constraint(session: Session):
    """
    Verifies that ProductAttribute has a UNIQUE constraint on (product_id, attribute_name).
    """
    # 1. Create product
    product = Product(sku="SKF-6205", brand="SKF", product_name="Bearing 6205", category="Bearings")
    session.add(product)
    session.commit()

    # 2. Add first attribute value
    attr1 = ProductAttribute(
        product_id=product.id,
        attribute_name="seal_type",
        display_name="Seal Type",
        raw_value="2RS",
        normalized_value="2RS",
        data_type=AttributeDataType.category,
        confidence=0.98,
        status=AttributeStatus.extracted,
        source_type="document"
    )
    session.add(attr1)
    session.commit()

    # 3. Attempting to add second attribute value for the same name triggers IntegrityError
    attr2 = ProductAttribute(
        product_id=product.id,
        attribute_name="seal_type",
        display_name="Seal Type",
        raw_value="2Z",
        normalized_value="2Z",
        data_type=AttributeDataType.category,
        confidence=0.95,
        status=AttributeStatus.extracted,
        source_type="document"
    )
    session.add(attr2)
    with pytest.raises(IntegrityError):
        session.commit()

def test_cache_key_uniqueness(session: Session):
    """
    Verifies that cache_key has a UNIQUE constraint enforced at database level.
    """
    entry1 = CacheEntry(
        cache_key="unique_key_123",
        cache_type=CacheType.extraction,
        input_hash="hash1",
        result_reference="ref1",
        cache_status=CacheStatus.valid
    )
    session.add(entry1)
    session.commit()

    entry2 = CacheEntry(
        cache_key="unique_key_123",  # Duplicate key
        cache_type=CacheType.extraction,
        input_hash="hash2",
        result_reference="ref2",
        cache_status=CacheStatus.valid
    )
    session.add(entry2)
    with pytest.raises(IntegrityError):
        session.commit()

def test_cache_reconstruction_on_redis_loss(session: Session):
    """
    Verifies that CacheService recovers keys from PostgreSQL and populates
    Redis if the Redis accelerator cache was cleared/lost.
    """
    service = CacheService(session)
    # Mock Redis client with dummy dict in memory
    redis_mock = {}
    
    class MockRedis:
        def get(self, key):
            return redis_mock.get(key)
        def set(self, key, val, ex=None):
            redis_mock[key] = str(val)
    
    service.redis_client = MockRedis()

    # Create persistent cache entry in DB
    entry = CacheEntry(
        cache_key="my_cache_key",
        cache_type=CacheType.extraction,
        input_hash="inputhash123",
        result_reference="serialized_data_abc",
        cache_status=CacheStatus.valid
    )
    session.add(entry)
    session.commit()

    # Simulate Redis loss: mock starts empty
    assert len(redis_mock) == 0

    # Query CacheService. It should fetch from Postgres, return it, and populate Redis
    result = service.get_cache("my_cache_key")
    assert result == "serialized_data_abc"
    assert redis_mock.get("my_cache_key") == "serialized_data_abc"

def test_duplicate_pair_normalization(session: Session):
    """
    Verifies that DuplicateService normalizes candidate registration, enforcing
    canonical ordering (product_id < candidate_product_id) to prevent duplicate pairs.
    """
    # Create actual products in database to satisfy foreign key constraints
    product1 = Product(sku="SKU-A", brand="BrandA", product_name="Product A", category="Cat")
    product2 = Product(sku="SKU-B", brand="BrandA", product_name="Product B", category="Cat")
    session.add(product1)
    session.add(product2)
    session.commit()

    p1_id = product1.id
    p2_id = product2.id

    # Sort ids to know which is lower
    low_id, high_id = (p1_id, p2_id) if p1_id < p2_id else (p2_id, p1_id)

    service = DuplicateService(session)
    
    # 1. Insert A -> B
    candidate1 = service.add_duplicate_candidate(
        p1=p1_id,
        p2=p2_id,
        similarity_score=0.92,
        detection_method=DuplicateMethod.sku_match
    )
    
    assert candidate1.product_id == low_id
    assert candidate1.candidate_product_id == high_id

    # 2. Insert B -> A (should fetch/update the same entry instead of duplicating)
    candidate2 = service.add_duplicate_candidate(
        p1=p2_id,
        p2=p1_id,
        similarity_score=0.95,
        detection_method=DuplicateMethod.sku_match
    )

    assert candidate2.id == candidate1.id
    assert candidate2.similarity_score == 0.95

    # Check constraint: same product id raises error
    with pytest.raises(ValueError):
        service.add_duplicate_candidate(p1=p1_id, p2=p1_id, similarity_score=1.0, detection_method=DuplicateMethod.sku_match)

def test_product_version_snapshot_reconstruction(session: Session):
    """
    Verifies that updating a product correctly saves snapshots inside ProductVersion,
    allowing comparison and full state reconstruction.
    """
    service = ProductService(session)
    
    # Create product
    prod_data = {
        "sku": "SKF-6205",
        "brand": "SKF",
        "product_name": "Deep Groove Bearing",
        "category": "Bearings",
        "attributes": {"bore": "25mm"},
        "features": ["High Speed"]
    }
    product = service.create_product(prod_data, actor_type=ActorType.ai)
    
    # Verify version 1 snapshot
    stmt = select(ProductVersion).where(ProductVersion.product_id == product.id)
    versions = list(session.exec(stmt).all())
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert versions[0].snapshot["product_name"] == "Deep Groove Bearing"
    assert versions[0].snapshot["attributes"] == {"bore": "25mm"}

    # Update product
    service.update_product(
        product_id=product.id,
        updated_data={"product_name": "Enriched SKF Bearing", "attributes": {"bore": "25mm", "outer": "52mm"}},
        change_summary="Add outer diameter",
        actor_type=ActorType.user
    )

    # Verify version 2 snapshot
    stmt = select(ProductVersion).where(ProductVersion.product_id == product.id).order_by(ProductVersion.version_number.asc())
    versions = list(session.exec(stmt).all())
    assert len(versions) == 2
    assert versions[0].snapshot["product_name"] == "Deep Groove Bearing"
    assert versions[1].snapshot["product_name"] == "Enriched SKF Bearing"
    assert versions[1].snapshot["attributes"] == {"bore": "25mm", "outer": "52mm"}

def test_foreign_key_delete_cascade(session: Session):
    """
    Verifies that cascade delete paths clean up child attributes and version snapshot
    records when a product is deleted, but SET NULL behaviors are safe.
    """
    product = Product(sku="M-100", brand="Motorola", product_name="Sensor M1", category="Sensors")
    session.add(product)
    session.commit()

    attr = ProductAttribute(
        product_id=product.id,
        attribute_name="voltage",
        display_name="Voltage",
        raw_value="12V",
        data_type=AttributeDataType.numeric,
        confidence=1.0,
        status=AttributeStatus.verified,
        source_type="manual"
    )
    session.add(attr)
    session.commit()

    # Add evidence
    source = Source(source_type=SourceType.manual, name="Manual Input Source")
    session.add(source)
    session.commit()

    evidence = AttributeEvidence(
        attribute_id=attr.id,
        source_id=source.id,
        evidence_text="Verified voltage: 12V"
    )
    session.add(evidence)
    session.commit()

    # Verify count before delete
    assert len(session.exec(select(ProductAttribute)).all()) == 1
    assert len(session.exec(select(AttributeEvidence)).all()) == 1

    # Delete product
    session.delete(product)
    session.commit()

    # ProductAttribute should be cascades-deleted
    assert len(session.exec(select(ProductAttribute)).all()) == 0
    # AttributeEvidence should also be deleted via cascade from attribute delete
    assert len(session.exec(select(AttributeEvidence)).all()) == 0
    # Source should still exist (ON DELETE SET NULL / independent entity)
    assert len(session.exec(select(Source)).all()) == 1

def test_full_relationship_traversal(session: Session):
    """
    Verifies relationship hierarchy traversal: Product -> Attribute -> Evidence -> Source.
    """
    # 1. Create Product
    product = Product(sku="V-200", brand="Asco", product_name="Solenoid Valve", category="Valves")
    session.add(product)
    session.commit()

    # 2. Create Source & Doc
    doc = Document(filename="valve_specs.pdf", storage_key="valves/1.pdf", file_hash="hash123", mime_type="application/pdf", file_size=1024)
    session.add(doc)
    session.commit()

    source = Source(source_type=SourceType.document, name="Datasheet PDF", document_id=doc.id)
    session.add(source)
    session.commit()

    # 3. Create Attribute
    attr = ProductAttribute(
        product_id=product.id,
        attribute_name="pressure_rating",
        display_name="Pressure Rating",
        raw_value="10 bar",
        data_type=AttributeDataType.numeric,
        confidence=0.99,
        status=AttributeStatus.extracted,
        source_type="document"
    )
    session.add(attr)
    session.commit()

    # 4. Create Evidence
    evidence = AttributeEvidence(
        attribute_id=attr.id,
        source_id=source.id,
        document_id=doc.id,
        page_number=2,
        evidence_text="Max pressure: 10 bar"
    )
    session.add(evidence)
    session.commit()

    # Traverse Product -> Attribute -> Evidence -> Source -> Document
    db_attr = session.exec(select(ProductAttribute).where(ProductAttribute.product_id == product.id)).first()
    assert db_attr is not None
    assert db_attr.attribute_name == "pressure_rating"

    db_evidence = session.exec(select(AttributeEvidence).where(AttributeEvidence.attribute_id == db_attr.id)).first()
    assert db_evidence is not None
    assert db_evidence.evidence_text == "Max pressure: 10 bar"
    assert db_evidence.page_number == 2

    db_source = session.get(Source, db_evidence.source_id)
    assert db_source is not None
    assert db_source.name == "Datasheet PDF"
    assert db_source.document_id == doc.id


def test_get_product_endpoint_attributes_dictionary(session: Session):
    """
    Verifies that GET /api/v1/products/{product_id} populates the 'attributes'
    dictionary with ProductAttribute data keyed by attribute_name.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_session

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)

        product = Product(
            sku="TEST-MOTOR-100",
            brand="CatalogIQ",
            product_name="Test Industrial Motor",
            category="Electric Motors"
        )
        session.add(product)
        session.commit()

        attr1 = ProductAttribute(
            product_id=product.id,
            attribute_name="rated_power",
            display_name="Rated Power",
            raw_value="5.5 kW",
            normalized_value=5.5,
            unit="kW",
            data_type=AttributeDataType.numeric,
            confidence=0.95,
            status=AttributeStatus.verified,
            source_type="deterministic"
        )
        attr2 = ProductAttribute(
            product_id=product.id,
            attribute_name="rated_voltage",
            display_name="Rated Voltage",
            raw_value="230 V",
            normalized_value=230,
            unit="V",
            data_type=AttributeDataType.numeric,
            confidence=0.95,
            status=AttributeStatus.verified,
            source_type="deterministic"
        )
        session.add(attr1)
        session.add(attr2)
        session.commit()

        # 1. Test GET /api/v1/products/{product_id}
        res = client.get(f"/api/v1/products/{product.id}")
        assert res.status_code == 200
        data = res.json()
        assert "attributes" in data
        assert len(data["attributes"]) == 2
        assert "rated_power" in data["attributes"]
        assert data["attributes"]["rated_power"]["value"] == 5.5
        assert data["attributes"]["rated_power"]["unit"] == "kW"
        assert data["attributes"]["rated_power"]["display_name"] == "Rated Power"
        assert data["attributes"]["rated_power"]["status"] == "verified"
        assert data["attributes"]["rated_power"]["source_type"] == "deterministic"

        # 2. Test GET /api/v1/products/{product_id}/attributes
        res_list = client.get(f"/api/v1/products/{product.id}/attributes")
        assert res_list.status_code == 200
        attrs_list = res_list.json()
        assert len(attrs_list) == 2
    finally:
        app.dependency_overrides.clear()


def test_get_product_complete_details_envelope_and_contract(session: Session):
    """
    Verifies that GET /api/v1/products/{product_id}/details returns the complete
    consolidated envelope required by the Product Details frontend view:
    - product base dict
    - attributes list
    - evidence list
    - validation summary
    - enrichment envelope
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_session

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)

        product = Product(
            sku="NORTON-45",
            brand="Norton",
            product_name="4-1/2 in Flap Disc",
            category="Abrasives & Polishers>Flap Discs & Flap Wheels",
            quality_score=95.0,
            status="verified"
        )
        session.add(product)
        session.commit()

        attr = ProductAttribute(
            product_id=product.id,
            attribute_name="wheel_diameter",
            display_name="Wheel Diameter",
            raw_value="4-1/2 in",
            normalized_value=4.5,
            unit="in",
            data_type=AttributeDataType.numeric,
            confidence=0.98,
            status=AttributeStatus.verified,
            source_type="document"
        )
        session.add(attr)
        session.commit()

        evid = AttributeEvidence(
            attribute_id=attr.id,
            product_id=product.id,
            evidence_text="4-1/2 in flap disc",
            page_number=1,
            extraction_method="table_parser"
        )
        session.add(evid)
        session.commit()

        # 1. Test GET /api/v1/products/{product_id}/details
        res = client.get(f"/api/v1/products/{product.id}/details")
        assert res.status_code == 200
        data = res.json()

        assert "product" in data
        assert data["product"]["id"] == str(product.id)
        assert data["product"]["sku"] == "NORTON-45"
        assert data["product"]["brand"] == "Norton"
        assert "attributes" in data["product"]

        assert "attributes" in data
        assert isinstance(data["attributes"], list)
        assert len(data["attributes"]) == 1
        assert data["attributes"][0]["attribute_name"] == "wheel_diameter"

        assert "evidence" in data
        assert isinstance(data["evidence"], list)
        assert len(data["evidence"]) == 1
        assert data["evidence"][0]["evidence_text"] == "4-1/2 in flap disc"

        assert "validation" in data
        assert "quality_score" in data["validation"]

        assert "enrichment" in data

        # 2. Test 404 on non-existent product ID
        missing_id = uuid.uuid4()
        res_404 = client.get(f"/api/v1/products/{missing_id}/details")
        assert res_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_product_details_structured_commerce_format_milwaukee_49_94_0013(session: Session):
    """
    Verifies that GET /api/v1/products/{id}/details returns structured commerce content
    conforming to Unilog delivery standard for Milwaukee 49-94-0013:
    - INPUT — Part_Desc
    - Classpath
    - Brand / MPN
    - Invoice Desc (<=40 char, CAPS)
    - Mobile Desc (60–80 char)
    - Product Title / Short Desc
    - Long Description
    - Attributes
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_session

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)

        product = Product(
            sku="49-94-0013",
            brand="Milwaukee",
            product_name="5 in x .045 in x 7/8 in Cut-Off Disc",
            description="5 in x .045 in x 7/8 in Metal Cut-Off Wheel Type 1",
            category="Abrasives & Polishers>Flap Discs & Flap Wheels",
            quality_score=96.0,
            status="verified"
        )
        session.add(product)
        session.commit()

        attr1 = ProductAttribute(
            product_id=product.id,
            attribute_name="Diameter",
            display_name="Diameter",
            raw_value="5 in",
            normalized_value="5",
            unit="in",
            data_type=AttributeDataType.numeric,
            confidence=0.98,
            status=AttributeStatus.verified,
            source_type="document"
        )
        attr2 = ProductAttribute(
            product_id=product.id,
            attribute_name="Thickness",
            display_name="Thickness",
            raw_value=".045 in",
            normalized_value=".045",
            unit="in",
            data_type=AttributeDataType.numeric,
            confidence=0.98,
            status=AttributeStatus.verified,
            source_type="document"
        )
        attr3 = ProductAttribute(
            product_id=product.id,
            attribute_name="Arbor Size",
            display_name="Arbor Size",
            raw_value="7/8 in",
            normalized_value="7/8",
            unit="in",
            data_type=AttributeDataType.numeric,
            confidence=0.98,
            status=AttributeStatus.verified,
            source_type="document"
        )
        session.add(attr1)
        session.add(attr2)
        session.add(attr3)
        session.commit()

        res = client.get(f"/api/v1/products/{product.id}/details")
        assert res.status_code == 200
        data = res.json()

        # 1. Product Identity & Input
        assert data["product"]["sku"] == "49-94-0013"
        assert data["product"]["brand"] == "Milwaukee"
        assert data["product"]["description"] == "5 in x .045 in x 7/8 in Metal Cut-Off Wheel Type 1"
        assert data["product"]["category"] == "Abrasives & Polishers>Flap Discs & Flap Wheels"

        # 2. Structured Delivery Descriptions in Enrichment
        enrichment = data["enrichment"]
        assert enrichment["invoice_desc"] is not None
        assert len(enrichment["invoice_desc"]) <= 40
        assert enrichment["invoice_desc"] == enrichment["invoice_desc"].upper()
        assert "CUT OFF DISC" in enrichment["invoice_desc"]

        assert enrichment["mobile_desc"] is not None
        assert "Milwaukee" in enrichment["mobile_desc"]
        assert "49-94-0013" in enrichment["mobile_desc"]

        assert enrichment["short_description"] is not None
        assert "Milwaukee" in enrichment["short_description"]

        assert enrichment["long_desc"] is not None
        assert "Milwaukee" in enrichment["long_desc"]

        # 3. Normalized Attributes List
        assert len(data["attributes"]) == 3
    finally:
        app.dependency_overrides.clear()


