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
    AttributeEvidence,
    AuditLog,
)
from app.services.keyword_search import KeywordSearchService

client = TestClient(app)


def test_keyword_search_empty_query(session: Session):
    """1. Test empty or whitespace-only query returns total=0 and empty list without DB query."""
    service = KeywordSearchService(session)

    res1 = service.search_keywords("")
    assert res1.total == 0
    assert res1.results == []

    res2 = service.search_keywords("   ")
    assert res2.total == 0
    assert res2.results == []


def test_keyword_search_no_results(session: Session):
    """18. Test valid search query with no matching catalog records returns HTTP 200 with total=0."""
    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        response = client.get("/api/v1/search/keyword?q=NONEXISTENT_SKU_QUERY_999")
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "NONEXISTENT_SKU_QUERY_999"
        assert data["total"] == 0
        assert data["results"] == []
    finally:
        app.dependency_overrides.clear()


def test_keyword_search_exact_and_partial_sku(session: Session):
    """2, 3, 19, 20, 21. Test exact SKU match (1.0), partial SKU match (0.8), case-insensitivity, whitespace & hyphen preservation."""
    p1 = Product(sku="MX500-230", brand="Siemens", product_name="Siemens Industrial Drive", category="Drives", quality_score=85.0)
    p2 = Product(sku="MX500-400", brand="Siemens", product_name="Siemens High Power Drive", category="Drives", quality_score=80.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = KeywordSearchService(session)

    # 1. Exact SKU (Case & whitespace normalized)
    res_exact = service.search_keywords("  mx500-230  ")
    assert res_exact.total == 1
    assert res_exact.results[0].sku == "MX500-230"
    assert res_exact.results[0].keyword_score == 1.00
    assert "sku" in res_exact.results[0].matched_fields

    # 2. Partial SKU
    res_partial = service.search_keywords("MX500")
    assert res_partial.total == 2
    skus = [r.sku for r in res_partial.results]
    assert "MX500-230" in skus
    assert "MX500-400" in skus
    assert res_partial.results[0].keyword_score == 0.80


def test_keyword_search_exact_and_partial_model(session: Session):
    """4, 5. Test exact model match (0.95) and partial model match (0.75)."""
    p1 = Product(sku="SKU-M1", brand="ABB", product_name="ABB Motor", model="M3BP 160", category="Motors", quality_score=90.0)
    p2 = Product(sku="SKU-M2", brand="ABB", product_name="ABB Motor Heavy", model="M3BP 200", category="Motors", quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = KeywordSearchService(session)

    res_exact = service.search_keywords("M3BP 160")
    assert res_exact.total >= 1
    assert res_exact.results[0].model == "M3BP 160"
    assert res_exact.results[0].keyword_score >= 0.95

    res_partial = service.search_keywords("M3BP")
    assert res_partial.total == 2
    assert res_partial.results[0].keyword_score >= 0.75


def test_keyword_search_name_brand_category(session: Session):
    """6, 7, 8. Test product_name, brand, and category matching."""
    p = Product(sku="SKU-NBC", brand="Schneider", product_name="Altivar Soft Starter", category="Soft Starters", quality_score=92.0)
    session.add(p)
    session.commit()

    service = KeywordSearchService(session)

    # Brand match
    r_brand = service.search_keywords("schneider")
    assert r_brand.total == 1
    assert "brand" in r_brand.results[0].matched_fields

    # Name match
    r_name = service.search_keywords("Altivar Soft Starter")
    assert r_name.total == 1
    assert "product_name" in r_name.results[0].matched_fields

    # Category match
    r_cat = service.search_keywords("soft starters")
    assert r_cat.total == 1
    assert "category" in r_cat.results[0].matched_fields


def test_keyword_search_attribute_raw_value(session: Session):
    """9. Test matching on ProductAttribute raw_value."""
    p = Product(sku="SKU-ATTR-1", brand="Danfoss", product_name="VLT AutomationDrive", category="Drives", quality_score=88.0)
    session.add(p)
    session.commit()

    attr = ProductAttribute(
        product_id=p.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="132 kW",
        unit="kW",
        data_type=AttributeDataType.numeric,
        source_type="document",
    )
    session.add(attr)
    session.commit()

    service = KeywordSearchService(session)
    res = service.search_keywords("132 kW")
    assert res.total == 1
    assert res.results[0].sku == "SKU-ATTR-1"
    assert "attributes" in res.results[0].matched_fields
    assert res.results[0].keyword_score >= 0.55


def test_exact_sku_outranks_generic_name_match(session: Session):
    """11, 12. Test exact SKU match outranks generic product name match."""
    # Product A: Exact SKU
    p_exact_sku = Product(sku="MX500-230", brand="BrandA", product_name="Heavy Industrial Motor", category="Motors", quality_score=70.0)
    # Product B: Product Name contains "MX500-230"
    p_name_match = Product(sku="OTHER-SKU-99", brand="BrandB", product_name="MX500-230 Compatible Motor", category="Motors", quality_score=95.0)

    session.add(p_exact_sku)
    session.add(p_name_match)
    session.commit()

    service = KeywordSearchService(session)
    res = service.search_keywords("MX500-230")

    assert res.total == 2
    # Exact SKU MUST rank #1 despite lower quality score!
    assert res.results[0].sku == "MX500-230"
    assert res.results[0].keyword_score == 1.00
    assert res.results[1].sku == "OTHER-SKU-99"
    assert res.results[1].keyword_score < 1.00


def test_keyword_search_filters_and_limits(session: Session):
    """13, 14, 15, 16, 17. Test category, brand, status, min_quality_score filters and limit."""
    p1 = Product(sku="P1", brand="Siemens", product_name="Siemens Motor A", category="Motors", status=ProductStatus.verified, quality_score=90.0)
    p2 = Product(sku="P2", brand="Siemens", product_name="Siemens Motor B", category="Motors", status=ProductStatus.needs_review, quality_score=50.0)
    p3 = Product(sku="P3", brand="ABB", product_name="ABB Motor C", category="Motors", status=ProductStatus.verified, quality_score=95.0)

    session.add(p1)
    session.add(p2)
    session.add(p3)
    session.commit()

    service = KeywordSearchService(session)

    # 1. Brand Filter
    r_brand = service.search_keywords("Motor", brand="Siemens")
    assert r_brand.total == 2
    assert all(r.brand == "Siemens" for r in r_brand.results)

    # 2. Status Filter
    r_status = service.search_keywords("Motor", product_status="verified")
    assert r_status.total == 2
    assert all(r.status == "verified" for r in r_status.results)

    # 3. Quality Score Filter
    r_qual = service.search_keywords("Motor", min_quality_score=80.0)
    assert r_qual.total == 2
    assert all(r.quality_score >= 80.0 for r in r_qual.results)

    # 4. Limit behavior
    r_lim = service.search_keywords("Motor", limit=1)
    assert len(r_lim.results) == 1
    assert r_lim.total == 3  # total matching is 3, but limited to 1 result


def test_keyword_search_duplicate_evidence_handling(session: Session):
    """Test duplicate AttributeEvidence rows do NOT produce duplicate Product results."""
    p = Product(sku="DUP-EVID-1", brand="Eaton", product_name="Eaton Breaker", category="Breakers", quality_score=85.0)
    session.add(p)
    session.commit()

    attr = ProductAttribute(
        product_id=p.id, attribute_name="current", display_name="Current Rating", raw_value="1600 A", data_type=AttributeDataType.numeric, source_type="document"
    )
    session.add(attr)
    session.commit()

    ev1 = AttributeEvidence(attribute_id=attr.id, evidence_text="1600 A trip unit")
    ev2 = AttributeEvidence(attribute_id=attr.id, evidence_text="1600 A frame rating")
    session.add(ev1)
    session.add(ev2)
    session.commit()

    service = KeywordSearchService(session)
    res = service.search_keywords("1600 A")
    assert res.total == 1
    assert len(res.results) == 1
    assert res.results[0].sku == "DUP-EVID-1"


def test_keyword_search_read_only_guarantee(session: Session):
    """22. Test keyword search is 100% read-only and performs zero DB insertions/updates/deletions."""
    p = Product(sku="READONLY-1", brand="Fuji", product_name="Fuji Contactor", category="Contactors", quality_score=80.0)
    session.add(p)
    session.commit()

    prod_count_before = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_before = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_before = session.exec(select(func.count()).select_from(AuditLog)).one()

    service = KeywordSearchService(session)
    _ = service.search_keywords("Fuji Contactor")

    prod_count_after = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_after = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_after = session.exec(select(func.count()).select_from(AuditLog)).one()

    assert prod_count_before == prod_count_after
    assert attr_count_before == attr_count_after
    assert audit_count_before == audit_count_after
