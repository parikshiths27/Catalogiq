"""
Qdrant Vector DB Service.
Wraps QdrantClient to handle collection creation, vector upserts, vector deletion, and similarity searches.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, Range, VectorParams

from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """
    Abstraction layer over QdrantClient for CatalogIQ vector indexing and semantic retrieval.
    """

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 10.0):
        self.url = url or settings.QDRANT_URL
        self.api_key = api_key or settings.QDRANT_API_KEY
        self.timeout = timeout
        self._client: Optional[QdrantClient] = None
        self._is_healthy: Optional[bool] = None
        self._last_health_check: float = 0.0

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url, api_key=self.api_key, timeout=self.timeout)
        return self._client

    def health_check(self) -> bool:
        """Returns True if Qdrant instance is reachable and healthy (cached for 30s)."""
        import time
        now = time.time()
        if self._is_healthy is not None and (now - self._last_health_check) < 30.0:
            return self._is_healthy

        self._last_health_check = now
        try:
            self.client.get_collections()
            self._is_healthy = True
            return True
        except Exception as e:
            self._is_healthy = False
            logger.warning(f"Qdrant health check failed ({self.url}): {e}")
            return False

    def ensure_collection_exists(
        self,
        collection_name: Optional[str] = None,
        vector_size: int = 384,
        distance: Distance = Distance.COSINE,
    ) -> bool:
        """
        Creates Qdrant collection automatically if it does not already exist.

        Args:
            collection_name: Name of collection. Defaults to settings.QDRANT_COLLECTION_NAME.
            vector_size: Vector dimensions derived from actual embedding provider.
            distance: Vector distance metric (default: COSINE).

        Returns:
            True if collection is ready.
        """
        import time
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
        last_err = None
        for attempt in range(2):
            try:
                collections_res = self.client.get_collections()
                existing_names = [c.name for c in collections_res.collections]

                if target_collection not in existing_names:
                    logger.info(
                        f"Creating Qdrant collection '{target_collection}' with vector_size={vector_size}, distance={distance}"
                    )
                    self.client.create_collection(
                        collection_name=target_collection,
                        vectors_config=VectorParams(size=vector_size, distance=distance),
                    )
                    # Create payload indexes so filtering on category, manufacturer, status, quality_score works out-of-the-box
                    try:
                        for field in ["category", "manufacturer", "status"]:
                            self.client.create_payload_index(
                                collection_name=target_collection,
                                field_name=field,
                                field_schema=rest_models.PayloadSchemaType.KEYWORD,
                            )
                        self.client.create_payload_index(
                            collection_name=target_collection,
                            field_name="quality_score",
                            field_schema=rest_models.PayloadSchemaType.FLOAT,
                        )
                    except Exception as e:
                        logger.debug(f"Payload index creation note: {e}")
                return True
            except Exception as e:
                last_err = e
                time.sleep(0.3)

        logger.error(f"Failed to ensure Qdrant collection '{target_collection}': {last_err}")
        raise last_err

    def upsert_product_vector(
        self,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
        collection_name: Optional[str] = None,
    ) -> bool:
        """
        Upserts a single product point (vector + payload) into Qdrant idempotently.

        Args:
            point_id: Deterministic UUID string derived from product_id.
            vector: Embedding vector float array.
            payload: Structured JSON payload metadata.
            collection_name: Qdrant collection name.

        Returns:
            True on success.
        """
        import time
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
        self.ensure_collection_exists(target_collection, vector_size=len(vector))

        point = PointStruct(id=point_id, vector=vector, payload=payload)

        last_err = None
        for attempt in range(2):
            try:
                self.client.upsert(collection_name=target_collection, points=[point])
                logger.info(f"Successfully upserted point {point_id} to collection '{target_collection}'")
                return True
            except Exception as e:
                last_err = e
                time.sleep(0.3)

        logger.error(f"Failed to upsert point {point_id} to Qdrant collection '{target_collection}': {last_err}")
        raise last_err

    def search_vectors(
        self,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Performs vector similarity search with optional payload filters.

        Args:
            query_vector: Embedding vector of natural language search query.
            limit: Maximum search results to return.
            filters: Dictionary of metadata filter criteria.
            collection_name: Target collection name.

        Returns:
            List of dict objects with keys 'id', 'score', 'payload'.
        """
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
        self.ensure_collection_exists(target_collection, vector_size=len(query_vector))

        query_filter = self._build_filter(filters)

        try:
            if hasattr(self.client, "query_points"):
                res_obj = self.client.query_points(
                    collection_name=target_collection,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                results = res_obj.points if hasattr(res_obj, "points") else res_obj
            elif hasattr(self.client, "search"):
                results = self.client.search(
                    collection_name=target_collection,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
            else:
                res_obj = self.client.search_points(
                    collection_name=target_collection,
                    vector=query_vector,
                    filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                results = res_obj.result if hasattr(res_obj, "result") else res_obj

            hits = []
            for item in results:
                hits.append(
                    {
                        "id": str(item.id),
                        "score": float(item.score),
                        "payload": item.payload or {},
                    }
                )
            return hits
        except Exception as e:
            logger.error(f"Qdrant search error in collection '{target_collection}': {e}")
            raise

    def delete_vector(self, point_id: str, collection_name: Optional[str] = None) -> bool:
        """Deletes a vector point from Qdrant by point_id."""
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
        try:
            self.client.delete(
                collection_name=target_collection,
                points_selector=rest_models.PointIdsList(points=[point_id]),
            )
            logger.info(f"Deleted vector point {point_id} from collection '{target_collection}'")
            return True
        except Exception as e:
            logger.error(f"Failed to delete vector point {point_id}: {e}")
            return False

    def count_points(self, collection_name: Optional[str] = None) -> int:
        """Returns total point count in specified collection."""
        target_collection = collection_name or settings.QDRANT_COLLECTION_NAME
        try:
            res = self.client.count(collection_name=target_collection)
            return res.count
        except Exception:
            return 0

    def _build_filter(self, filters: Optional[Dict[str, Any]]) -> Optional[Filter]:
        """Constructs Qdrant Filter model supporting lists and range bounds."""
        if not filters:
            return None

        must_conditions = []

        # Category
        cat_val = filters.get("category")
        if cat_val:
            if isinstance(cat_val, list):
                if len(cat_val) == 1:
                    must_conditions.append(FieldCondition(key="category", match=MatchValue(value=str(cat_val[0]))))
                elif len(cat_val) > 1:
                    must_conditions.append(FieldCondition(key="category", match=rest_models.MatchAny(any=[str(c) for c in cat_val])))
            else:
                must_conditions.append(FieldCondition(key="category", match=MatchValue(value=str(cat_val))))

        # Brand / Manufacturer
        brand_val = filters.get("brand") or filters.get("manufacturer")
        if brand_val:
            if isinstance(brand_val, list):
                if len(brand_val) == 1:
                    must_conditions.append(FieldCondition(key="manufacturer", match=MatchValue(value=str(brand_val[0]))))
                elif len(brand_val) > 1:
                    must_conditions.append(FieldCondition(key="manufacturer", match=rest_models.MatchAny(any=[str(b) for b in brand_val])))
            else:
                must_conditions.append(FieldCondition(key="manufacturer", match=MatchValue(value=str(brand_val))))

        # Status
        status_val = filters.get("status")
        if status_val:
            if isinstance(status_val, list):
                if len(status_val) == 1:
                    must_conditions.append(FieldCondition(key="status", match=MatchValue(value=str(status_val[0]))))
                elif len(status_val) > 1:
                    must_conditions.append(FieldCondition(key="status", match=rest_models.MatchAny(any=[str(s) for s in status_val])))
            else:
                must_conditions.append(FieldCondition(key="status", match=MatchValue(value=str(status_val))))

        # Quality score range
        range_kwargs = {}
        if filters.get("min_quality_score") is not None:
            range_kwargs["gte"] = float(filters["min_quality_score"])
        if filters.get("max_quality_score") is not None:
            range_kwargs["lte"] = float(filters["max_quality_score"])
        if range_kwargs:
            must_conditions.append(FieldCondition(key="quality_score", range=Range(**range_kwargs)))

        if not must_conditions:
            return None

        return Filter(must=must_conditions)
