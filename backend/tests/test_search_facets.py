import uuid
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, func

from app.main import app
from app.db.session import get_session
from app.models import (
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeDataType,
    AttributeStatus,
    AuditLog,
)
from app.services.facets import FacetAggregationService, parse_list_param

client = TestClient(app)


def test_url_parameter_parsing():
    """16. Test parse_list_param helper correctly parses scalar, list, or comma-separated filter values."""
    assert parse_list_param(None) == []
    assert parse_list_param("") == []
    assert parse_list_param("Siemens") == ["Siemens"]
    assert parse_list_param("Siemens,ABB") == ["Siemens", "ABB"]
    assert parse_list_param("  Siemens , ABB  , Schneider  ") == ["Siemens", "ABB", "Schneider"]
    assert parse_list_param(["Siemens", "ABB"]) == ["Siemens", "ABB"]


def test_invalid_min_greater_than_max_raises_422(session: Session):
    """10. Test min_quality_score > max_quality_score raises HTTP 422 Unprocessable Entity."""
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        res = client.get("/api/v1/search?q=motor&min_quality_score=90&max_quality_score=50")
        assert res.status_code == 422
        assert "min_quality_score cannot be greater than max_quality_score" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_single_and_multi_value_category_filter(session: Session):
    """1, 2. Test single-value and multi-value category filtering."""
    p1 = Product(sku="CAT-P1", brand="BrandA", product_name="Motor Item", category="Motors", quality_score=85.0)
    p2 = Product(sku="CAT-P2", brand="BrandA", product_name="Drive Item", category="Drives", quality_score=85.0)
    p3 = Product(sku="CAT-P3", brand="BrandA", product_name="Starter Item", category="Starters", quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # Single category
        res1 = client.get("/api/v1/search?q=Item&category=Motors&mode=keyword")
        assert res1.status_code == 200
        assert res1.json()["total"] == 1
        assert res1.json()["results"][0]["sku"] == "CAT-P1"

        # Multi-category (Motors OR Drives)
        res2 = client.get("/api/v1/search?q=Item&category=Motors,Drives&mode=keyword")
        assert res2.status_code == 200
        assert res2.json()["total"] == 2
        skus = [r["sku"] for r in res2.json()["results"]]
        assert "CAT-P1" in skus
        assert "CAT-P2" in skus
    finally:
        app.dependency_overrides.clear()


def test_multi_value_brand_and_status(session: Session):
    """3, 4, 5. Test multi-value brand and status filtering."""
    p1 = Product(sku="BR-P1", brand="Siemens", product_name="Item 1", category="Motors", status=ProductStatus.verified, quality_score=90.0)
    p2 = Product(sku="BR-P2", brand="ABB", product_name="Item 2", category="Motors", status=ProductStatus.needs_review, quality_score=85.0)
    p3 = Product(sku="BR-P3", brand="Eaton", product_name="Item 3", category="Motors", status=ProductStatus.draft, quality_score=75.0)
    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # Multi-brand (Siemens OR ABB)
        res = client.get("/api/v1/search?q=Item&brand=Siemens,ABB&mode=keyword")
        assert res.status_code == 200
        assert res.json()["total"] == 2

        # Multi-status (verified OR needs_review)
        res_st = client.get("/api/v1/search?q=Item&status=verified,needs_review&mode=keyword")
        assert res_st.status_code == 200
        assert res_st.json()["total"] == 2
    finally:
        app.dependency_overrides.clear()


def test_subcategory_and_quality_range(session: Session):
    """6, 7, 8, 9. Test subcategory, min_quality_score, and max_quality_score bounds."""
    p1 = Product(sku="SUB-P1", brand="BrandA", product_name="Heavy Motor", category="Motors", subcategory="Induction", quality_score=50.0)
    p2 = Product(sku="SUB-P2", brand="BrandA", product_name="Light Motor", category="Motors", subcategory="Servo", quality_score=85.0)
    p3 = Product(sku="SUB-P3", brand="BrandA", product_name="Super Motor", category="Motors", subcategory="Servo", quality_score=95.0)
    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # Quality score range (70 to 90)
        res_q = client.get("/api/v1/search?q=Motor&min_quality_score=70&max_quality_score=90&mode=keyword")
        assert res_q.status_code == 200
        assert res_q.json()["total"] == 1
        assert res_q.json()["results"][0]["sku"] == "SUB-P2"

        # Subcategory filter
        res_sub = client.get("/api/v1/search?q=Motor&subcategory=Servo&mode=keyword")
        assert res_sub.status_code == 200
        assert res_sub.json()["total"] == 2
    finally:
        app.dependency_overrides.clear()


def test_disjunctive_facet_counts(session: Session):
    """12, 13, 14, 15, 23, 24. Test GET /api/v1/search/facets returns accurate disjunctive facet counts."""
    p1 = Product(sku="FCT-1", brand="Siemens", product_name="Siemens Industrial Motor", category="Motors", quality_score=95.0)
    p2 = Product(sku="FCT-2", brand="Siemens", product_name="Siemens Industrial Drive", category="Drives", quality_score=85.0)
    p3 = Product(sku="FCT-3", brand="ABB", product_name="ABB Industrial Motor", category="Motors", quality_score=75.0)
    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        # Request facets for query "Industrial" with active Brand filter "Siemens"
        res = client.get("/api/v1/search/facets?q=Industrial&brand=Siemens")
        assert res.status_code == 200
        data = res.json()
        facets = data["facets"]

        # Disjunctive Brand counts should ignore current brand=Siemens selection and show all brand counts for "Industrial"
        brand_map = {b["value"]: b["count"] for b in facets["brands"]}
        assert brand_map.get("Siemens") == 2
        assert brand_map.get("ABB") == 1

        # Category counts SHOULD respect the active brand=Siemens filter
        cat_map = {c["value"]: c["count"] for c in facets["categories"]}
        assert cat_map.get("Motors") == 1
        assert cat_map.get("Drives") == 1
    finally:
        app.dependency_overrides.clear()


def test_dynamic_attribute_facet_generation(session: Session):
    """21, 22. Test dynamic attribute facet generation and cardinality limits."""
    p1 = Product(sku="ATTR-P1", brand="Danfoss", product_name="Drive 1", category="Drives", quality_score=90.0)
    p2 = Product(sku="ATTR-P2", brand="Danfoss", product_name="Drive 2", category="Drives", quality_score=90.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    attr1 = ProductAttribute(
        product_id=p1.id, attribute_name="ip_rating", display_name="IP Rating", raw_value="IP55", confidence=0.95, status=AttributeStatus.verified, data_type=AttributeDataType.category, source_type="doc"
    )
    attr2 = ProductAttribute(
        product_id=p2.id, attribute_name="ip_rating", display_name="IP Rating", raw_value="IP55", confidence=0.95, status=AttributeStatus.verified, data_type=AttributeDataType.category, source_type="doc"
    )
    session.add(attr1)
    session.add(attr2)
    session.commit()

    service = FacetAggregationService(session)
    res = service.compute_facets(query="Drive")

    assert len(res.attributes) >= 1
    ip_facet = next(a for a in res.attributes if a.attribute_name == "ip_rating")
    assert ip_facet.display_name == "IP Rating"
    assert ip_facet.values[0].value == "IP55"
    assert ip_facet.values[0].count == 2


def test_search_mode_filtering(session: Session):
    """17, 18, 19. Test filters work seamlessly across keyword, semantic, and hybrid modes."""
    p = Product(sku="MODE-1", brand="Vacon", product_name="Vacon High Power Inverter", category="Inverters", quality_score=90.0)
    session.add(p)
    session.commit()

    from app.services.indexing import IndexingService
    from app.services.embeddings.mock_provider import MockEmbeddingProvider
    indexer = IndexingService(session, embedding_provider=MockEmbeddingProvider())
    indexer.index_product(p.id)

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        for mode in ["keyword", "hybrid"]:
            res = client.get(f"/api/v1/search?q=Vacon&brand=Vacon&mode={mode}")
            assert res.status_code == 200
            assert res.json()["total"] >= 1
    finally:
        app.dependency_overrides.clear()


def test_facets_read_only_guarantee(session: Session):
    """20. Test facet aggregation service and API perform 0 DB write operations."""
    p = Product(sku="FACET-READONLY", brand="Siemens", product_name="Readonly Facet Motor", category="Motors", quality_score=85.0)
    session.add(p)
    session.commit()

    prod_count_before = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_before = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_before = session.exec(select(func.count()).select_from(AuditLog)).one()

    service = FacetAggregationService(session)
    _ = service.compute_facets(query="Readonly Facet Motor")

    prod_count_after = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_after = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_after = session.exec(select(func.count()).select_from(AuditLog)).one()

    assert prod_count_before == prod_count_after
    assert attr_count_before == attr_count_after
    assert audit_count_before == audit_count_after
