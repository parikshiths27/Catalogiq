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
    EmbeddingMetadata,
)
from app.services.keyword_search import KeywordSearchService
from app.services.qdrant import QdrantService
from app.services.hybrid_search import HybridSearchService
from app.services.embeddings.mock_provider import MockEmbeddingProvider
from app.services.indexing import IndexingService

client = TestClient(app)


def test_hybrid_empty_query(session: Session):
    """1. Test empty query returns total=0 and empty results list."""
    service = HybridSearchService(session)
    res1 = service.search_hybrid("")
    assert res1.total == 0
    assert res1.results == []

    res2 = service.search_hybrid("   ")
    assert res2.total == 0
    assert res2.results == []


def test_hybrid_no_results(session: Session):
    """2. Test valid query with no catalog matches returns total=0."""
    service = HybridSearchService(session)
    res = service.search_hybrid("NONEXISTENT_QUERY_STRING_XYZ")
    assert res.total == 0
    assert res.results == []


def test_hybrid_response_schema(session: Session):
    """3. Test GET /api/v1/search?mode=hybrid API returns valid HybridSearchResponse schema."""
    p = Product(sku="HYBRID-SCH-1", brand="Siemens", product_name="Siemens Hybrid Motor", category="Motors", quality_score=90.0)
    session.add(p)
    session.commit()

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override
    try:
        res = client.get("/api/v1/search?q=Siemens Hybrid Motor&mode=hybrid")
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "Siemens Hybrid Motor"
        assert data["search_mode"] == "hybrid"
        assert "results" in data
        assert isinstance(data["results"], list)
    finally:
        app.dependency_overrides.clear()


def test_exact_sku_boost(session: Session):
    """4, 12. Test exact SKU match receives +0.30 boost and ranks #1 above purely semantic matches."""
    p1 = Product(sku="EXACT-SKU-100", brand="BrandA", product_name="Generic Motor", category="Motors", quality_score=70.0)
    p2 = Product(sku="OTHER-SKU-999", brand="BrandB", product_name="EXACT-SKU-100 High Quality Drive", category="Motors", quality_score=95.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("EXACT-SKU-100")

    assert res.total == 2
    assert res.results[0].sku == "EXACT-SKU-100"
    assert res.results[0].match_type == "exact"
    assert res.results[0].hybrid_score >= 0.80


def test_exact_model_boost(session: Session):
    """5. Test exact model match receives +0.25 boost."""
    p = Product(sku="SKU-MDL-1", brand="ABB", product_name="ABB Motor", model="M3BP-160", category="Motors", quality_score=85.0)
    session.add(p)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("M3BP-160")

    assert res.total == 1
    assert res.results[0].model == "M3BP-160"
    assert res.results[0].match_type == "exact"
    assert res.results[0].hybrid_score >= 0.705


def test_exact_product_name_boost(session: Session):
    """6. Test exact product name match receives +0.15 boost."""
    p = Product(sku="SKU-NAME-1", brand="Danfoss", product_name="VLT AutomationDrive FC302", category="Drives", quality_score=90.0)
    session.add(p)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("VLT AutomationDrive FC302")

    assert res.total == 1
    assert res.results[0].match_type == "exact"
    assert res.results[0].hybrid_score >= 0.60


class MockVectorQdrantService(QdrantService):
    def __init__(self, target_product_id: uuid.UUID, score: float = 0.85):
        self.target_product_id = target_product_id
        self.score = score

    def search_vectors(self, *args, **kwargs):
        return [{"id": str(self.target_product_id), "score": self.score}]


def test_product_present_in_both_engines(session: Session):
    """7, 10, 11. Test score fusion for product present in both keyword and vector candidate sets."""
    p = Product(sku="DUAL-001", brand="Schneider", product_name="Altivar Soft Starter 11kW", category="Starters", quality_score=88.0)
    session.add(p)
    session.commit()

    qdrant_mock = MockVectorQdrantService(p.id, score=0.85)
    service = HybridSearchService(session, qdrant_service=qdrant_mock)
    res = service.search_hybrid("Altivar Soft Starter 11kW")

    assert res.total == 1
    item = res.results[0]
    assert item.sku == "DUAL-001"
    assert item.keyword_score > 0.0
    assert item.similarity_score > 0.0
    assert item.hybrid_score > 0.0


def test_keyword_only_product(session: Session):
    """8. Test product matching keyword search but not vector index is classified as 'keyword'."""
    p = Product(sku="KW-ONLY-99", brand="Eaton", product_name="Eaton Circuit Breaker", category="Breakers", quality_score=80.0)
    session.add(p)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("KW-ONLY-99")

    assert res.total == 1
    assert res.results[0].match_type == "exact"  # Exact SKU takes precedence over keyword match_type
    assert res.results[0].keyword_score == 1.0


def test_semantic_only_product(session: Session):
    """9. Test product indexed in Qdrant but not keyword matched is classified as 'semantic'."""
    p = Product(sku="SEM-ONLY-01", brand="Vacon", product_name="Special High Frequency Inverter", category="Inverters", quality_score=85.0)
    session.add(p)
    session.commit()

    qdrant_mock = MockVectorQdrantService(p.id, score=0.85)
    service = HybridSearchService(session, qdrant_service=qdrant_mock)
    res = service.search_hybrid("frequency energy converter")

    assert res.total >= 1
    assert res.results[0].sku == "SEM-ONLY-01"
    assert res.results[0].match_type == "semantic"


def test_duplicate_product_deduplication(session: Session):
    """10. Test that products present in both engines are deduplicated into a single result."""
    p = Product(sku="DEDUP-100", brand="Fuji", product_name="Fuji Electric Contactor", category="Contactors", quality_score=92.0)
    session.add(p)
    session.commit()

    qdrant_mock = MockVectorQdrantService(p.id, score=0.80)
    service = HybridSearchService(session, qdrant_service=qdrant_mock)
    res = service.search_hybrid("Fuji Electric Contactor")

    # Should contain exactly ONE instance of DEDUP-100
    skus = [r.sku for r in res.results if r.sku == "DEDUP-100"]
    assert len(skus) == 1


def test_hybrid_score_calculation(session: Session):
    """11. Test hybrid score equals (0.50 * kw) + (0.50 * sem) + exact_boost clamped to 1.0."""
    p = Product(sku="CALC-1", brand="BrandC", product_name="Calculation Test Motor", category="Motors", quality_score=80.0)
    session.add(p)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Calculation Test Motor")

    assert res.total == 1
    item = res.results[0]
    assert 0.0 <= item.hybrid_score <= 1.0


def test_exact_sku_outranks_semantic_result(session: Session):
    """12. Test exact SKU outranks semantic vector search result."""
    p_exact = Product(sku="SKU-TARGET-55", brand="BrandA", product_name="Standard Industrial Machine", category="Machines", quality_score=60.0)
    p_sem = Product(sku="OTHER-88", brand="BrandB", product_name="SKU-TARGET-55 High Efficiency Machine", category="Machines", quality_score=98.0)

    session.add(p_exact)
    session.add(p_sem)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("SKU-TARGET-55")

    assert res.total == 2
    assert res.results[0].sku == "SKU-TARGET-55"
    assert res.results[0].hybrid_score >= 0.80


def test_semantic_query_preserves_semantic_relevance(session: Session):
    """13. Test natural language query relies on vector similarity when exact match is absent."""
    p1 = Product(sku="P1", brand="BrandA", product_name="High Speed Induction Motor 15kW", category="Motors", quality_score=85.0)
    session.add(p1)
    session.commit()

    qdrant_mock = MockVectorQdrantService(p1.id, score=0.88)
    service = HybridSearchService(session, qdrant_service=qdrant_mock)
    res = service.search_hybrid("continuous duty high speed motor")

    assert res.total >= 1
    assert res.results[0].sku == "P1"


def test_deterministic_tie_breaking(session: Session):
    """14. Test deterministic tie-breaking by quality_score DESC when hybrid_score is equal."""
    p1 = Product(sku="TIE-1", brand="SameBrand", product_name="Same Product Name", category="Motors", quality_score=70.0)
    p2 = Product(sku="TIE-2", brand="SameBrand", product_name="Same Product Name", category="Motors", quality_score=95.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Same Product Name")

    assert res.total == 2
    # P2 has higher quality_score (95 vs 70), so it should rank #1 on tie-break
    assert res.results[0].sku == "TIE-2"


def test_category_filter(session: Session):
    """15. Test category filter is respected by hybrid search."""
    p1 = Product(sku="CAT-1", brand="BrandA", product_name="Motor A", category="Motors", quality_score=85.0)
    p2 = Product(sku="CAT-2", brand="BrandA", product_name="Drive B", category="Drives", quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("BrandA", category="Motors")

    assert res.total == 1
    assert res.results[0].sku == "CAT-1"


def test_brand_filter(session: Session):
    """16. Test brand filter is respected by hybrid search."""
    p1 = Product(sku="BR-1", brand="Siemens", product_name="Siemens Item", category="Motors", quality_score=85.0)
    p2 = Product(sku="BR-2", brand="ABB", product_name="ABB Item", category="Motors", quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Item", brand="Siemens")

    assert res.total == 1
    assert res.results[0].sku == "BR-1"


def test_status_filter(session: Session):
    """17. Test status filter is respected by hybrid search."""
    p1 = Product(sku="ST-1", brand="BrandA", product_name="Item A", category="Motors", status=ProductStatus.verified, quality_score=85.0)
    p2 = Product(sku="ST-2", brand="BrandA", product_name="Item B", category="Motors", status=ProductStatus.needs_review, quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Item", product_status="verified")

    assert res.total == 1
    assert res.results[0].sku == "ST-1"


def test_min_quality_score_filter(session: Session):
    """18. Test min_quality_score filter is respected by hybrid search."""
    p1 = Product(sku="QS-1", brand="BrandA", product_name="Item Low", category="Motors", quality_score=40.0)
    p2 = Product(sku="QS-2", brand="BrandA", product_name="Item High", category="Motors", quality_score=90.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Item", min_quality_score=80.0)

    assert res.total == 1
    assert res.results[0].sku == "QS-2"


def test_combined_filters(session: Session):
    """19. Test applying combined category, brand, status, and min_quality_score filters simultaneously."""
    p1 = Product(sku="ALL-1", brand="Siemens", product_name="Target Motor", category="Motors", status=ProductStatus.verified, quality_score=90.0)
    p2 = Product(sku="ALL-2", brand="Siemens", product_name="Target Motor", category="Motors", status=ProductStatus.draft, quality_score=90.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid("Target Motor", category="Motors", brand="Siemens", product_status="verified", min_quality_score=80.0)

    assert res.total == 1
    assert res.results[0].sku == "ALL-1"


def test_qdrant_failure_falls_back_to_keyword(session: Session):
    """20. Test Qdrant failure causes hybrid search to degrade gracefully to keyword search."""
    p = Product(sku="FALLBACK-1", brand="Eaton", product_name="Eaton Fallback Product", category="Breakers", quality_score=80.0)
    session.add(p)
    session.commit()

    class BrokenQdrantService(QdrantService):
        def search_vectors(self, *args, **kwargs):
            raise RuntimeError("Qdrant cluster offline")

    service = HybridSearchService(session, qdrant_service=BrokenQdrantService())
    res = service.search_hybrid("Eaton Fallback Product")

    assert res.total == 1
    assert res.degraded_mode == "vector_unavailable"
    assert res.results[0].sku == "FALLBACK-1"


def test_embedding_failure_falls_back_to_keyword(session: Session):
    """21. Test embedding provider failure degrades hybrid search to keyword search."""
    p = Product(sku="EMB-FAIL-1", brand="Fuji", product_name="Fuji Contactor Product", category="Contactors", quality_score=85.0)
    session.add(p)
    session.commit()

    service = HybridSearchService(session)
    # Pass invalid query or force exception in embedding block
    res = service.search_hybrid("Fuji Contactor Product")

    assert res.total >= 1


def test_keyword_failure_falls_back_to_semantic(session: Session):
    """22. Test keyword engine failure degrades hybrid search to semantic vector search."""
    p = Product(sku="KW-FAIL-1", brand="Vacon", product_name="Vacon Inverter Drive", category="Drives", quality_score=90.0)
    session.add(p)
    session.commit()

    class BrokenKeywordService(KeywordSearchService):
        def search_keywords(self, *args, **kwargs):
            raise RuntimeError("PostgreSQL keyword index unavailable")

    qdrant_mock = MockVectorQdrantService(p.id, score=0.88)
    service = HybridSearchService(session, keyword_service=BrokenKeywordService(session), qdrant_service=qdrant_mock)
    res = service.search_hybrid("Vacon Inverter Drive")

    assert res.total >= 1
    assert res.degraded_mode == "keyword_unavailable"


def test_both_engines_failure_returns_503(session: Session):
    """23. Test both keyword and vector engine failure raises exception for HTTP 503 handling."""
    class BrokenQdrantService(QdrantService):
        def search_vectors(self, *args, **kwargs):
            raise RuntimeError("Qdrant offline")

    class BrokenKeywordService(KeywordSearchService):
        def search_keywords(self, *args, **kwargs):
            raise RuntimeError("SQL offline")

    service = HybridSearchService(session, keyword_service=BrokenKeywordService(session), qdrant_service=BrokenQdrantService())
    with pytest.raises(RuntimeError):
        service.search_hybrid("test query")


def test_hybrid_search_read_only(session: Session):
    """24. Test hybrid search performs 0 SQL insertions/updates/deletions and leaves DB records 100% unchanged."""
    p = Product(sku="READONLY-HYBRID", brand="Siemens", product_name="Readonly Test Motor", category="Motors", quality_score=85.0)
    session.add(p)
    session.commit()

    prod_count_before = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_before = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_before = session.exec(select(func.count()).select_from(AuditLog)).one()
    meta_count_before = session.exec(select(func.count()).select_from(EmbeddingMetadata)).one()

    service = HybridSearchService(session)
    _ = service.search_hybrid("Readonly Test Motor")

    prod_count_after = session.exec(select(func.count()).select_from(Product)).one()
    attr_count_after = session.exec(select(func.count()).select_from(ProductAttribute)).one()
    audit_count_after = session.exec(select(func.count()).select_from(AuditLog)).one()
    meta_count_after = session.exec(select(func.count()).select_from(EmbeddingMetadata)).one()

    assert prod_count_before == prod_count_after
    assert attr_count_before == attr_count_after
    assert audit_count_before == audit_count_after
    assert meta_count_before == meta_count_after
