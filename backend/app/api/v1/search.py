"""
Semantic Search API Router.
Exposes GET /api/v1/search and POST index management endpoints.
"""
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.config import settings
from app.db.session import get_session
from app.models import Product
from app.repositories import AttributeRepository, ProductRepository
from app.services.embeddings.factory import get_embedding_provider
from app.services.indexing import IndexingService
from app.services.qdrant import QdrantService
from app.services.keyword_search import KeywordSearchService, KeywordSearchResponse
from app.services.hybrid_search import HybridSearchService, HybridSearchResponse

router = APIRouter(prefix="/search")


class SearchResultItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    category: str
    manufacturer: str
    model: Optional[str] = None
    quality_score: float
    similarity_score: float
    status: str
    commerce_description: Optional[str] = None
    short_description: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    attributes: List[Dict[str, Any]] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    total: int
    results: List[SearchResultItem]


@router.get("", response_model=Any)
@router.get("/", response_model=Any)
def search_products(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of search results to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand/manufacturer"),
    product_status: Optional[str] = Query(None, alias="status", description="Filter by product status"),
    min_quality_score: Optional[float] = Query(None, description="Filter by minimum quality score"),
    mode: Optional[str] = Query("semantic", description="Search mode: 'semantic', 'keyword', or 'hybrid'"),
    session: Session = Depends(get_session),
):
    """
    Search endpoint supporting 'semantic' (default), 'keyword', or 'hybrid' modes.
    Default mode 'semantic' maintains 100% Phase 6 backward compatibility.
    """
    if not q or not q.strip():
        if mode == "hybrid":
            return HybridSearchResponse(query=q or "", search_mode="hybrid", total=0, results=[])
        elif mode == "keyword":
            return KeywordSearchResponse(query=q or "", total=0, results=[])
        return SearchResponse(query=q or "", total=0, results=[])

    if mode == "hybrid":
        hybrid_service = HybridSearchService(session)
        return hybrid_service.search_hybrid(
            query=q,
            limit=limit,
            category=category,
            brand=brand,
            product_status=product_status,
            min_quality_score=min_quality_score,
        )
    elif mode == "keyword":
        keyword_service = KeywordSearchService(session)
        return keyword_service.search_keywords(
            query=q,
            limit=limit,
            category=category,
            brand=brand,
            product_status=product_status,
            min_quality_score=min_quality_score,
        )

    # 1. Embed query
    provider = get_embedding_provider()
    try:
        query_vector = provider.embed_text(q.strip())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate query embedding: {e}",
        )

    # 2. Qdrant Similarity Search
    qdrant = QdrantService()
    filters = {}
    if category:
        filters["category"] = category
    if brand:
        filters["brand"] = brand
    if product_status:
        filters["status"] = product_status
    if min_quality_score is not None:
        filters["min_quality_score"] = min_quality_score

    try:
        hits = qdrant.search_vectors(
            query_vector=query_vector,
            limit=limit,
            filters=filters,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Qdrant vector retrieval service unavailable: {e}",
        )

    if not hits:
        return SearchResponse(query=q, total=0, results=[])

    # 3. Retrieve authoritative Product records from PostgreSQL
    product_repo = ProductRepository(session)
    attr_repo = AttributeRepository(session)
    results: List[SearchResultItem] = []

    for hit in hits:
        point_id_str = hit["id"]
        try:
            prod_id = uuid.UUID(point_id_str)
        except ValueError:
            continue

        product = product_repo.get_by_id(prod_id)
        if not product:
            continue

        # Format attributes
        db_attributes = attr_repo.list_by_product(product.id)
        formatted_attrs = []
        for attr in db_attributes:
            formatted_attrs.append(
                {
                    "attribute_name": attr.attribute_name,
                    "display_name": attr.display_name,
                    "raw_value": attr.raw_value,
                    "normalized_value": attr.normalized_value,
                    "unit": attr.unit,
                    "confidence": attr.confidence,
                    "status": attr.status.value if hasattr(attr.status, "value") else str(attr.status),
                }
            )

        # Normalize score (Qdrant Cosine returns -1.0 to 1.0; map to float)
        score_raw = float(hit["score"])
        # Standardize score display (0.0 to 1.0 range)
        score_normalized = round(max(0.0, min(1.0, score_raw)), 4)

        item = SearchResultItem(
            product_id=str(product.id),
            product_name=product.product_name,
            sku=product.sku,
            category=product.category,
            manufacturer=product.brand,
            model=product.model,
            quality_score=float(product.quality_score),
            similarity_score=score_normalized,
            status=product.status.value if hasattr(product.status, "value") else str(product.status),
            commerce_description=product.commerce_description or product.description,
            short_description=None,
            features=product.features or [],
            applications=product.applications or [],
            attributes=formatted_attrs,
        )
        results.append(item)

    return SearchResponse(
        query=q,
        total=len(results),
        results=results,
    )


@router.get("/keyword", response_model=KeywordSearchResponse)
def search_products_keyword(
    q: str = Query(..., description="Text keyword search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of search results to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand/manufacturer"),
    product_status: Optional[str] = Query(None, alias="status", description="Filter by product status"),
    min_quality_score: Optional[float] = Query(None, description="Filter by minimum quality score"),
    session: Session = Depends(get_session),
):
    """
    Normal/lexical PostgreSQL keyword search endpoint.
    Performs case-insensitive exact and substring matching on product identity, SKU, model,
    brand, category, and technical specifications with deterministic relevance scoring.
    """
    keyword_service = KeywordSearchService(session)
    return keyword_service.search_keywords(
        query=q,
        limit=limit,
        category=category,
        brand=brand,
        product_status=product_status,
        min_quality_score=min_quality_score,
    )


@router.get("/hybrid", response_model=HybridSearchResponse)
def search_products_hybrid(
    q: str = Query(..., description="Hybrid search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of search results to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand/manufacturer"),
    product_status: Optional[str] = Query(None, alias="status", description="Filter by product status"),
    min_quality_score: Optional[float] = Query(None, description="Filter by minimum quality score"),
    session: Session = Depends(get_session),
):
    """
    Dedicated Hybrid Search endpoint combining PostgreSQL keyword search and Qdrant semantic vector search.
    """
    hybrid_service = HybridSearchService(session)
    return hybrid_service.search_hybrid(
        query=q,
        limit=limit,
        category=category,
        brand=brand,
        product_status=product_status,
        min_quality_score=min_quality_score,
    )


@router.post("/index/{product_id}")
def index_product_endpoint(
    product_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    """Admin endpoint to index or re-index a single product into Qdrant."""
    indexer = IndexingService(session)
    try:
        res = indexer.index_product(product_id)
        return res
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to index product: {e}",
        )


@router.post("/reindex-all")
def reindex_all_endpoint(
    session: Session = Depends(get_session),
):
    """Admin endpoint to re-index all products into Qdrant."""
    indexer = IndexingService(session)
    try:
        res = indexer.index_all_products()
        return res
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reindex products: {e}",
        )
