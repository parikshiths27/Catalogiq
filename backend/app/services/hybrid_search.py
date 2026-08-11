"""
Hybrid Search Engine Service for CatalogIQ.
Orchestrates PostgreSQL Keyword Search and Qdrant Semantic Vector Retrieval with
weighted score fusion, exact-match boosting, graceful degradation, and batch hydration.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from app.core.config import settings
from app.models import Product, ProductAttribute, ProductStatus
from app.services.embeddings.factory import get_embedding_provider
from app.services.keyword_search import KeywordSearchService
from app.services.qdrant import QdrantService

logger = logging.getLogger(__name__)


class HybridSearchResultItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    brand: str
    manufacturer: str
    model: Optional[str] = None
    category: str
    status: str
    quality_score: float
    hybrid_score: float
    keyword_score: float
    similarity_score: float
    match_type: str  # "exact", "hybrid", "keyword", "semantic"
    matched_fields: List[str] = Field(default_factory=list)
    commerce_description: Optional[str] = None
    short_description: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    attributes: List[Dict[str, Any]] = Field(default_factory=list)


class HybridSearchResponse(BaseModel):
    query: str
    search_mode: str  # "hybrid", "semantic", "keyword"
    degraded_mode: Optional[str] = None  # None, "vector_unavailable", "embedding_failed", "keyword_unavailable"
    total: int
    results: List[HybridSearchResultItem]


class HybridSearchService:
    """
    Hybrid Search Engine combining PostgreSQL lexical keyword retrieval and
    Qdrant vector semantic search with weighted fusion and fallback resilience.
    """

    def __init__(
        self,
        session: Session,
        keyword_service: Optional[KeywordSearchService] = None,
        qdrant_service: Optional[QdrantService] = None,
    ):
        self.session = session
        self.keyword_service = keyword_service or KeywordSearchService(session)
        self.qdrant_service = qdrant_service or QdrantService()

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        product_status: Optional[str] = None,
        min_quality_score: Optional[float] = None,
    ) -> HybridSearchResponse:
        """
        Executes hybrid search across keyword and vector engines with candidate pool fusion.

        Args:
            query: User search text query.
            limit: Top N results to return.
            category: Optional category filter.
            brand: Optional brand/manufacturer filter.
            product_status: Optional status filter.
            min_quality_score: Optional quality score threshold filter.

        Returns:
            HybridSearchResponse containing merged, ranked results and degradation metadata.
        """
        if not query or not query.strip():
            return HybridSearchResponse(
                query=query or "",
                search_mode="hybrid",
                degraded_mode=None,
                total=0,
                results=[],
            )

        raw_query = query.strip()
        query_norm = raw_query.lower()
        k_candidate = max(30, limit * 3)

        keyword_hits: Dict[uuid.UUID, Tuple[float, List[str]]] = {}
        vector_hits: Dict[uuid.UUID, float] = {}

        degraded_mode: Optional[str] = None
        keyword_failed = False
        vector_failed = False

        # 1. Retrieve Keyword Candidates
        try:
            kw_res = self.keyword_service.search_keywords(
                query=raw_query,
                limit=k_candidate,
                category=category,
                brand=brand,
                product_status=product_status,
                min_quality_score=min_quality_score,
            )
            for item in kw_res.results:
                try:
                    pid = uuid.UUID(item.product_id)
                    keyword_hits[pid] = (item.keyword_score, item.matched_fields)
                except ValueError:
                    continue
        except Exception as e:
            logger.error(f"Keyword search engine failure in hybrid search: {e}")
            keyword_failed = True
            degraded_mode = "keyword_unavailable"

        # 2. Retrieve Vector Semantic Candidates
        query_vector: Optional[List[float]] = None
        if not vector_failed:
            try:
                provider = get_embedding_provider()
                query_vector = provider.embed_text(raw_query)
            except Exception as e:
                logger.error(f"Embedding generation failure in hybrid search: {e}")
                vector_failed = True
                degraded_mode = "embedding_failed"

        if query_vector is not None and not vector_failed:
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
                hits = self.qdrant_service.search_vectors(
                    query_vector=query_vector,
                    limit=k_candidate,
                    filters=filters,
                )
                for hit in hits:
                    try:
                        pid = uuid.UUID(hit["id"])
                        score_raw = float(hit["score"])
                        score_norm = round(max(0.0, min(1.0, score_raw)), 4)
                        vector_hits[pid] = score_norm
                    except ValueError:
                        continue
            except Exception as e:
                logger.error(f"Qdrant vector engine failure in hybrid search: {e}")
                vector_failed = True
                degraded_mode = "vector_unavailable"

        # If both engines failed, raise RuntimeError
        if keyword_failed and vector_failed:
            raise RuntimeError("Both keyword and vector search engines are unavailable.")

        # Candidate pool union
        candidate_ids = list(set(keyword_hits.keys()).union(set(vector_hits.keys())))

        if not candidate_ids:
            return HybridSearchResponse(
                query=raw_query,
                search_mode="hybrid",
                degraded_mode=degraded_mode,
                total=0,
                results=[],
            )

        # 3. Batch PostgreSQL Hydration (Union of candidate product IDs)
        product_filters = [Product.id.in_(candidate_ids)]
        if category and category.strip():
            product_filters.append(func.lower(Product.category) == category.strip().lower())
        if brand and brand.strip():
            product_filters.append(func.lower(Product.brand) == brand.strip().lower())
        if product_status and product_status.strip():
            product_filters.append(func.lower(Product.status) == product_status.strip().lower())
        if min_quality_score is not None:
            product_filters.append(Product.quality_score >= float(min_quality_score))

        candidate_products = self.session.exec(
            select(Product).where(*product_filters)
        ).all()

        if not candidate_products:
            return HybridSearchResponse(
                query=raw_query,
                search_mode="hybrid",
                degraded_mode=degraded_mode,
                total=0,
                results=[],
            )

        valid_product_ids = [p.id for p in candidate_products]

        # Batch load attributes
        attrs_stmt = select(ProductAttribute).where(ProductAttribute.product_id.in_(valid_product_ids))
        all_attrs = self.session.exec(attrs_stmt).all()

        product_attrs_map: Dict[uuid.UUID, List[ProductAttribute]] = {}
        for attr in all_attrs:
            product_attrs_map.setdefault(attr.product_id, []).append(attr)

        # 4. Score Fusion, Exact Match Detection, and Classification
        hybrid_results: List[HybridSearchResultItem] = []

        for p in candidate_products:
            kw_score, matched_fields = keyword_hits.get(p.id, (0.0, []))
            sem_score = vector_hits.get(p.id, 0.0)

            # Check exact match rules
            p_sku_norm = (p.sku or "").strip().lower()
            p_model_norm = (p.model or "").strip().lower()
            p_name_norm = (p.product_name or "").strip().lower()

            is_exact_sku = p_sku_norm == query_norm
            is_exact_model = bool(p_model_norm and p_model_norm == query_norm)
            is_exact_name = p_name_norm == query_norm

            exact_boost = 0.0
            if is_exact_sku:
                exact_boost = 0.30
                if "sku" not in matched_fields:
                    matched_fields.append("sku")
            elif is_exact_model:
                exact_boost = 0.25
                if "model" not in matched_fields:
                    matched_fields.append("model")
            elif is_exact_name:
                exact_boost = 0.15
                if "product_name" not in matched_fields:
                    matched_fields.append("product_name")

            base_hybrid_score = (0.50 * kw_score) + (0.50 * sem_score)
            final_hybrid_score = round(min(1.0000, base_hybrid_score + exact_boost), 4)

            # Match Type Classification
            if is_exact_sku or is_exact_model or is_exact_name:
                match_type = "exact"
            elif p.id in keyword_hits and p.id in vector_hits:
                match_type = "hybrid"
            elif p.id in keyword_hits:
                match_type = "keyword"
            else:
                match_type = "semantic"

            # Format attributes
            p_attrs = product_attrs_map.get(p.id, [])
            formatted_attrs = [
                {
                    "attribute_name": a.attribute_name,
                    "display_name": a.display_name,
                    "raw_value": a.raw_value,
                    "normalized_value": a.normalized_value,
                    "unit": a.unit,
                    "confidence": a.confidence,
                    "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                }
                for a in p_attrs
            ]

            item = HybridSearchResultItem(
                product_id=str(p.id),
                product_name=p.product_name,
                sku=p.sku,
                brand=p.brand,
                manufacturer=p.brand,
                model=p.model,
                category=p.category,
                status=str(p.status.value if hasattr(p.status, "value") else p.status),
                quality_score=float(p.quality_score),
                hybrid_score=final_hybrid_score,
                keyword_score=kw_score,
                similarity_score=sem_score,
                match_type=match_type,
                matched_fields=matched_fields,
                commerce_description=p.commerce_description or p.description,
                short_description=None,
                features=p.features or [],
                applications=p.applications or [],
                attributes=formatted_attrs,
            )
            hybrid_results.append(item)

        # 5. Primary Sort: hybrid_score DESC, Secondary Sort: quality_score DESC
        hybrid_results.sort(key=lambda r: (r.hybrid_score, r.quality_score), reverse=True)

        return HybridSearchResponse(
            query=raw_query,
            search_mode="hybrid",
            degraded_mode=degraded_mode,
            total=len(hybrid_results),
            results=hybrid_results[:limit],
        )
