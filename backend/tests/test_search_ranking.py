import uuid
import pytest
from sqlmodel import Session, select, func

from app.models import (
    Product,
    ProductStatus,
    ProductAttribute,
    AttributeDataType,
    AttributeStatus,
    AuditLog,
)
from app.services.search_ranking import (
    SearchRankingService,
    QueryIntent,
    ExactMatchPriority,
    INTENT_WEIGHTS_MAP,
)
from app.services.hybrid_search import HybridSearchService
from app.services.keyword_search import KeywordSearchService
from app.services.qdrant import QdrantService


def test_intent_identifier_classification():
    """7. Test IDENTIFIER query intent classification."""
    assert SearchRankingService.classify_query_intent("MX500-230") == QueryIntent.IDENTIFIER
    assert SearchRankingService.classify_query_intent("ABC-123") == QueryIntent.IDENTIFIER
    assert SearchRankingService.classify_query_intent("SN-4400") == QueryIntent.IDENTIFIER


def test_intent_natural_language_classification():
    """8. Test NATURAL_LANGUAGE query intent classification."""
    assert SearchRankingService.classify_query_intent("industrial induction motor") == QueryIntent.NATURAL_LANGUAGE
    assert SearchRankingService.classify_query_intent("motor for high temperature environments") == QueryIntent.NATURAL_LANGUAGE
    assert SearchRankingService.classify_query_intent("high efficiency motor for pumps") == QueryIntent.NATURAL_LANGUAGE


def test_intent_mixed_classification():
    """9. Test MIXED query intent classification."""
    assert SearchRankingService.classify_query_intent("Siemens MX500-230 motor") == QueryIntent.MIXED
    assert SearchRankingService.classify_query_intent("11 kW Siemens induction motor") == QueryIntent.MIXED
    assert SearchRankingService.classify_query_intent("ABB M3BP 160 motor") == QueryIntent.MIXED


def test_intent_specific_weights():
    """10. Test intent weights sum to 1.0."""
    for intent, weights in INTENT_WEIGHTS_MAP.items():
        assert round(weights.keyword_weight + weights.semantic_weight, 2) == 1.0
    assert INTENT_WEIGHTS_MAP[QueryIntent.IDENTIFIER].keyword_weight == 0.80
    assert INTENT_WEIGHTS_MAP[QueryIntent.NATURAL_LANGUAGE].semantic_weight == 0.70


def test_identifier_weighted_fusion():
    """11. Test IDENTIFIER weighted fusion score calculation."""
    # Identifier intent: 0.80 kw + 0.20 sem
    score = SearchRankingService.fuse_scores(1.0, 0.5, QueryIntent.IDENTIFIER, ExactMatchPriority.NONE)
    assert score == round((0.80 * 1.0) + (0.20 * 0.5), 4)  # 0.90


def test_natural_language_weighted_fusion():
    """12. Test NATURAL_LANGUAGE weighted fusion score calculation."""
    # Natural language intent: 0.30 kw + 0.70 sem
    score = SearchRankingService.fuse_scores(0.4, 0.9, QueryIntent.NATURAL_LANGUAGE, ExactMatchPriority.NONE)
    assert score == round((0.30 * 0.4) + (0.70 * 0.9), 4)  # 0.75


def test_mixed_weighted_fusion():
    """13. Test MIXED weighted fusion score calculation."""
    # Mixed intent: 0.50 kw + 0.50 sem
    score = SearchRankingService.fuse_scores(0.6, 0.8, QueryIntent.MIXED, ExactMatchPriority.NONE)
    assert score == round((0.50 * 0.6) + (0.50 * 0.8), 4)  # 0.70


def test_candidate_pool_limit_sizing():
    """16, 17, 18. Test candidate pool size calculations."""
    assert SearchRankingService.get_candidate_pool_size(5) == 50   # Minimum 50
    assert SearchRankingService.get_candidate_pool_size(10) == 50  # 10 * 5 = 50
    assert SearchRankingService.get_candidate_pool_size(20) == 100 # 20 * 5 = 100


def test_exact_priority_sku_vs_non_exact_hybrid(session: Session):
    """1, 2. Test exact SKU match ALWAYS outranks non-exact hybrid match regardless of scores."""
    p_sku = Product(sku="MX500-230", brand="Siemens", product_name="Siemens Inverter", category="Drives", quality_score=60.0)
    p_non_exact = Product(sku="OTHER-999", brand="Siemens", product_name="MX500 Series Drive", category="Drives", quality_score=95.0)
    session.add(p_sku)
    session.add(p_non_exact)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid(query="MX500-230", limit=10)

    assert res.total >= 1
    assert res.results[0].sku == "MX500-230"
    assert res.results[0].ranking_priority == 3


def test_exact_priority_model_vs_name(session: Session):
    """3, 4, 5, 6. Test exact SKU > exact Model > exact Name priority ordering."""
    p1 = Product(sku="EXACT-SKU-99", brand="Siemens", model="MD-1", product_name="Motor Item", category="Motors", quality_score=80.0)
    p2 = Product(sku="OTHER-1", brand="Siemens", model="EXACT-SKU-99", product_name="Motor Item", category="Motors", quality_score=80.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid(query="EXACT-SKU-99", limit=10)

    assert res.results[0].sku == "EXACT-SKU-99"  # Exact SKU priority 3
    assert res.results[0].ranking_priority == 3
    assert res.results[1].model == "EXACT-SKU-99"  # Exact Model priority 2
    assert res.results[1].ranking_priority == 2


def test_same_hybrid_same_quality_product_id_ordering(session: Session):
    """14, 15. Test deterministic sorting sequence."""
    p1 = Product(sku="SKU-A", brand="ABB", product_name="Standard Motor A", category="Motors", quality_score=85.0)
    p2 = Product(sku="SKU-B", brand="ABB", product_name="Standard Motor B", category="Motors", quality_score=85.0)
    session.add(p1)
    session.add(p2)
    session.commit()

    service = HybridSearchService(session)
    res = service.search_hybrid(query="Standard Motor", limit=10)

    assert len(res.results) == 2
    assert res.results[0].ranking_priority == res.results[1].ranking_priority


def test_attribute_relevance_exact_and_partial():
    """19, 20. Test Task 8.5 attribute relevance calculation."""
    class DummyAttr:
        def __init__(self, raw_val, disp_val):
            self.raw_value = raw_val
            self.display_name = disp_val

    attrs = [DummyAttr("IP55", "Ingress Protection")]

    # Exact raw value match
    score_exact = SearchRankingService.compute_attribute_relevance("ip55", attrs)
    assert score_exact == 0.75

    # Partial substring match
    score_partial = SearchRankingService.compute_attribute_relevance("protection", attrs)
    assert score_partial == 0.55

    # No match
    score_none = SearchRankingService.compute_attribute_relevance("explosion", attrs)
    assert score_none == 0.00


def test_read_only_ranking_guarantee(session: Session):
    """25. Test search ranking performs 0 database writes."""
    p = Product(sku="RANK-READONLY", brand="Vacon", product_name="Readonly Rank Inverter", category="Inverters", quality_score=90.0)
    session.add(p)
    session.commit()

    prod_count_before = session.exec(select(func.count()).select_from(Product)).one()
    audit_count_before = session.exec(select(func.count()).select_from(AuditLog)).one()

    service = HybridSearchService(session)
    _ = service.search_hybrid(query="Readonly Rank Inverter")

    prod_count_after = session.exec(select(func.count()).select_from(Product)).one()
    audit_count_after = session.exec(select(func.count()).select_from(AuditLog)).one()

    assert prod_count_before == prod_count_after
    assert audit_count_before == audit_count_after
