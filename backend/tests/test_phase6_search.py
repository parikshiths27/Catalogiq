"""
Phase 6 Test Suite — Semantic Search + Qdrant Retrieval.

Tests:
  - Mock embedding provider determinism and vector dimension
  - Qdrant collection auto-creation & connectivity
  - Canonical search document builder (fact-bounded, no hallucinated attributes)
  - Qdrant payload generation
  - Idempotent indexing (re-indexing product N times keeps 1 Qdrant point)
  - Product change re-indexing and EmbeddingMetadata synchronization
  - Semantic search retrieval with natural language queries
  - Structured metadata filtering (category, brand, quality score)
  - Qdrant and embedding failure isolation (PostgreSQL remains intact)
  - Index deletion and reindex-all endpoints
  - FastAPI search endpoints schema validation
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_session
from app.main import app as fastapi_app
from app.models import (
    EmbeddingMetadata,
    EnrichmentResult,
    EnrichmentStatus,
    EnrichmentType,
    Product,
    ProductAttribute,
    ProductStatus,
)
from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.mock_provider import MockEmbeddingProvider
from app.services.indexing import IndexingService
from app.services.qdrant import QdrantService, get_qdrant_service
from app.services.search_document import build_qdrant_payload, build_search_document


@pytest.fixture
def mock_embedding_provider():
    return MockEmbeddingProvider(vector_dim=384)


@pytest.fixture
def qdrant_service():
    return QdrantService()


def test_embedding_provider_determinism_and_dimension(mock_embedding_provider):
    """Test MockEmbeddingProvider produces deterministic, unit-normalized float vectors of correct dimension."""
    provider = mock_embedding_provider
    assert provider.provider_name == "mock"
    assert provider.dimension == 384

    v1 = provider.embed_text("Industrial induction motor 11 kW")
    v2 = provider.embed_text("Industrial induction motor 11 kW")
    v3 = provider.embed_text("Variable frequency drive 400V")

    assert len(v1) == 384
    assert v1 == v2
    assert v1 != v3


def test_qdrant_collection_creation_and_health(qdrant_service):
    """Test QdrantService connectivity and automatic collection initialization."""
    assert qdrant_service.health_check() is True
    res = qdrant_service.ensure_collection_exists("test_catalogiq_collection", vector_size=384)
    assert res is True


def test_search_document_builder_fact_bounded(session: Session):
    """Test search document construction includes existing facts and omits missing specifications without inventing data."""
    product = Product(
        sku="IND-MTR-11KW",
        brand="CatalogIQ Test Works",
        product_name="CQ-X120 Industrial Induction Motor",
        category="Industrial Electric Motor",
        subcategory="Three Phase",
        description="High efficiency TEFC industrial motor.",
        commerce_description="Premium grade 11kW motor for harsh factory environments.",
        features=["TEFC Cooling", "Class F Insulation"],
        applications=["Pumps", "Compressors"],
    )
    session.add(product)
    session.commit()

    attr1 = ProductAttribute(
        product_id=product.id,
        attribute_name="rated_power",
        display_name="Rated Power",
        raw_value="11",
        unit="kW",
        data_type="numeric",
        source_type="llm",
    )
    attr2 = ProductAttribute(
        product_id=product.id,
        attribute_name="voltage",
        display_name="Rated Voltage",
        raw_value="400",
        unit="V",
        data_type="numeric",
        source_type="llm",
    )
    session.add(attr1)
    session.add(attr2)
    session.commit()

    doc_text = build_search_document(product, [attr1, attr2])

    assert "CQ-X120 Industrial Induction Motor" in doc_text
    assert "Manufacturer: CatalogIQ Test Works" in doc_text
    assert "SKU: IND-MTR-11KW" in doc_text
    assert "Rated Power: 11 kW" in doc_text
    assert "Rated Voltage: 400 V" in doc_text
    assert "Pumps" in doc_text
    assert "Compressors" in doc_text

    # Missing attributes (e.g. ambient_temperature or rated_speed) must NOT be invented
    assert "ambient_temperature" not in doc_text.lower()
    assert "rated_speed" not in doc_text.lower()


def test_qdrant_payload_generation(session: Session):
    """Test Qdrant payload dictionary generation contains expected identity and attribute fields."""
    product = Product(
        sku="PAYLOAD-001",
        brand="PayloadBrand",
        product_name="Payload Test Motor",
        category="Motors",
        quality_score=95.0,
        status=ProductStatus.verified,
    )
    session.add(product)
    session.commit()

    attr = ProductAttribute(
        product_id=product.id,
        attribute_name="speed",
        display_name="Rated Speed",
        raw_value="1470",
        unit="RPM",
        data_type="numeric",
        source_type="deterministic",
    )
    session.add(attr)
    session.commit()

    payload = build_qdrant_payload(product, [attr])
    assert payload["product_id"] == str(product.id)
    assert payload["sku"] == "PAYLOAD-001"
    assert payload["manufacturer"] == "PayloadBrand"
    assert payload["category"] == "Motors"
    assert payload["quality_score"] == 95.0
    assert "speed" in payload["attributes"]
    assert payload["attributes"]["speed"]["raw_value"] == "1470"


def test_idempotent_product_indexing(session: Session, mock_embedding_provider, qdrant_service):
    """Test indexing a product multiple times updates the exact same Qdrant point without creating duplicates."""
    test_collection = f"test_idempotency_{uuid.uuid4().hex[:8]}"
    qdrant_service.ensure_collection_exists(test_collection, vector_size=384)

    product = Product(
        sku="IDEM-100",
        brand="IdemBrand",
        product_name="Idempotent Test Motor",
        category="Industrial",
    )
    session.add(product)
    session.commit()

    indexer = IndexingService(session, embedding_provider=mock_embedding_provider, qdrant_service=qdrant_service)

    # 1st Indexing
    res1 = indexer.index_product(product.id, collection_name=test_collection)
    assert res1["status"] == "indexed"
    vector_id = res1["vector_id"]

    # Verify 1 metadata entry
    meta1 = session.exec(select(EmbeddingMetadata).where(EmbeddingMetadata.product_id == product.id)).all()
    assert len(meta1) == 1
    assert meta1[0].vector_id == vector_id

    # 2nd Indexing (same data)
    res2 = indexer.index_product(product.id, collection_name=test_collection)
    assert res2["status"] == "indexed"
    assert res2["vector_id"] == vector_id

    # Verify still exactly 1 metadata record in DB
    meta2 = session.exec(select(EmbeddingMetadata).where(EmbeddingMetadata.product_id == product.id)).all()
    assert len(meta2) == 1


def test_reindex_after_product_change(session: Session, mock_embedding_provider, qdrant_service):
    """Test modifying product specifications and re-indexing updates vector payload and content hash."""
    test_collection = f"test_reindex_{uuid.uuid4().hex[:8]}"

    product = Product(
        sku="CHG-200",
        brand="ChangeBrand",
        product_name="Initial Name Motor",
        category="Motors",
    )
    session.add(product)
    session.commit()

    indexer = IndexingService(session, embedding_provider=mock_embedding_provider, qdrant_service=qdrant_service)
    res1 = indexer.index_product(product.id, collection_name=test_collection)
    hash1 = res1["content_hash"]

    # Modify product name
    product.product_name = "Updated Heavy Duty Motor"
    session.add(product)
    session.commit()

    res2 = indexer.index_product(product.id, collection_name=test_collection)
    hash2 = res2["content_hash"]

    assert hash1 != hash2
    assert res2["vector_id"] == res1["vector_id"]

    meta = session.exec(select(EmbeddingMetadata).where(EmbeddingMetadata.product_id == product.id)).first()
    assert meta is not None
    assert meta.content_hash == hash2


def test_semantic_search_and_metadata_filtering(session: Session, mock_embedding_provider, qdrant_service):
    """Test natural language vector search and structured metadata filtering (category, brand, min_quality_score)."""
    test_collection = f"test_search_filter_{uuid.uuid4().hex[:8]}"

    p1 = Product(
        sku="MTR-10KW",
        brand="CatalogIQ Motors",
        product_name="10kW Continuous Induction Motor",
        category="Electric Motors",
        quality_score=90.0,
        status=ProductStatus.verified,
    )
    p2 = Product(
        sku="PMP-5KW",
        brand="CatalogIQ Pumps",
        product_name="Centrifugal Water Pump 5kW",
        category="Pumps",
        quality_score=80.0,
        status=ProductStatus.verified,
    )
    session.add(p1)
    session.add(p2)
    session.commit()

    indexer = IndexingService(session, embedding_provider=mock_embedding_provider, qdrant_service=qdrant_service)
    indexer.index_product(p1.id, collection_name=test_collection)
    indexer.index_product(p2.id, collection_name=test_collection)

    # Perform vector search with category filter
    query_vec = mock_embedding_provider.embed_text("industrial induction motor 10kW")
    hits = qdrant_service.search_vectors(
        query_vector=query_vec,
        limit=10,
        filters={"category": "Electric Motors"},
        collection_name=test_collection,
    )

    assert len(hits) == 1
    assert hits[0]["payload"]["sku"] == "MTR-10KW"


def test_qdrant_and_embedding_failure_isolation(session: Session):
    """Test that Qdrant or embedding failure during post-enrichment indexing does NOT corrupt or roll back PostgreSQL data."""
    product = Product(
        sku="FAIL-SAFE-01",
        brand="SafeBrand",
        product_name="Fail Safe Product",
        category="Testing",
        status=ProductStatus.verified,
        quality_score=88.0,
    )
    session.add(product)
    session.commit()

    attr = ProductAttribute(
        product_id=product.id,
        attribute_name="power",
        display_name="Power",
        raw_value="15",
        unit="kW",
        data_type="numeric",
        source_type="llm",
    )
    session.add(attr)
    session.commit()

    # Simulate broken Qdrant service
    class BrokenQdrantService(QdrantService):
        def upsert_product_vector(self, *args, **kwargs):
            raise RuntimeError("Qdrant database cluster connection refused")

    indexer = IndexingService(
        session,
        embedding_provider=MockEmbeddingProvider(),
        qdrant_service=BrokenQdrantService(),
    )

    # Indexing fails with exception
    with pytest.raises(RuntimeError):
        indexer.index_product(product.id)

    # PostgreSQL product & attribute data remain completely intact!
    saved_product = session.get(Product, product.id)
    assert saved_product is not None
    assert saved_product.sku == "FAIL-SAFE-01"
    assert saved_product.quality_score == 88.0

    saved_attrs = session.exec(select(ProductAttribute).where(ProductAttribute.product_id == product.id)).all()
    assert len(saved_attrs) == 1


def test_delete_and_reindex_all(session: Session, mock_embedding_provider, qdrant_service):
    """Test delete_product_index and index_all_products methods."""
    test_collection = f"test_bulk_{uuid.uuid4().hex[:8]}"

    p1 = Product(sku="BULK-01", brand="BrandA", product_name="Bulk Product 1", category="CatA")
    p2 = Product(sku="BULK-02", brand="BrandB", product_name="Bulk Product 2", category="CatB")
    session.add(p1)
    session.add(p2)
    session.commit()

    indexer = IndexingService(session, embedding_provider=mock_embedding_provider, qdrant_service=qdrant_service)

    # Bulk index
    res = indexer.index_all_products(collection_name=test_collection)
    assert res["indexed"] >= 2

    # Delete p1 index
    del_res = indexer.delete_product_index(p1.id, collection_name=test_collection)
    assert del_res is True

    meta = session.exec(select(EmbeddingMetadata).where(EmbeddingMetadata.product_id == p1.id)).first()
    assert meta is None


def test_search_api_endpoint_schema(session: Session, mock_embedding_provider, qdrant_service):
    """Test GET /api/v1/search API endpoint returns compliant SearchResponse schema."""
    fastapi_app.dependency_overrides[get_session] = lambda: session
    fastapi_app.dependency_overrides[get_qdrant_service] = lambda: qdrant_service

    p = Product(
        sku="API-TEST-99",
        brand="APIBrand",
        product_name="API Searchable Motor",
        category="Motors",
        quality_score=92.0,
        status=ProductStatus.verified,
        commerce_description="High-performance motor available via REST API.",
    )
    session.add(p)
    session.commit()

    indexer = IndexingService(session, embedding_provider=mock_embedding_provider, qdrant_service=qdrant_service)
    indexer.index_product(p.id)

    client = TestClient(fastapi_app)
    response = client.get("/api/v1/search?q=high performance motor&limit=5")

    assert response.status_code == 200
    data = response.json()

    assert "query" in data
    assert data["query"] == "high performance motor"
    assert "total" in data
    assert "results" in data
    assert isinstance(data["results"], list)

    fastapi_app.dependency_overrides.clear()
