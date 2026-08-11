"""
PostgreSQL Keyword Search Engine for CatalogIQ.
Provides deterministic lexical and exact text matching across Product identity,
brand, model, category, and technical attribute values.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from sqlmodel import Session, select, or_, and_, func
from sqlalchemy.orm import selectinload

from app.models import Product, ProductAttribute, ProductStatus

logger = logging.getLogger(__name__)


class KeywordSearchResultItem(BaseModel):
    product_id: str
    product_name: str
    sku: str
    brand: str
    model: Optional[str] = None
    category: str
    status: str
    quality_score: float
    keyword_score: float
    matched_fields: List[str] = Field(default_factory=list)


class KeywordSearchResponse(BaseModel):
    query: str
    total: int
    results: List[KeywordSearchResultItem]


class KeywordSearchService:
    """
    PostgreSQL-backed deterministic keyword and lexical search service.
    Performs case-insensitive exact and substring matching on Product identity
    and ProductAttribute specifications with multi-field scoring hierarchy.
    """

    def __init__(self, session: Session):
        self.session = session

    def search_keywords(
        self,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        product_status: Optional[str] = None,
        min_quality_score: Optional[float] = None,
    ) -> KeywordSearchResponse:
        """
        Performs keyword search against PostgreSQL product catalog.

        Args:
            query: User search text query string.
            limit: Maximum search results to return.
            category: Optional filter for product category.
            brand: Optional filter for brand / manufacturer.
            product_status: Optional filter for product status (draft, needs_review, verified).
            min_quality_score: Optional filter for minimum quality score threshold.

        Returns:
            KeywordSearchResponse containing query, total count, and ranked results.
        """
        if not query or not query.strip():
            return KeywordSearchResponse(query=query or "", total=0, results=[])

        raw_query = query.strip()
        query_lower = raw_query.lower()
        like_pattern = f"%{raw_query}%"

        # 1. Base Filter Conditions for Product
        product_filters = []
        if category and category.strip():
            product_filters.append(func.lower(Product.category) == category.strip().lower())
        if brand and brand.strip():
            product_filters.append(func.lower(Product.brand) == brand.strip().lower())
        if product_status and product_status.strip():
            product_filters.append(func.lower(Product.status) == product_status.strip().lower())
        if min_quality_score is not None:
            product_filters.append(Product.quality_score >= float(min_quality_score))

        # 2. Query for Product IDs matching Product fields
        product_text_match_condition = or_(
            Product.sku.ilike(like_pattern),
            Product.model.ilike(like_pattern),
            Product.product_name.ilike(like_pattern),
            Product.brand.ilike(like_pattern),
            Product.category.ilike(like_pattern),
        )

        matching_product_stmt = select(Product.id).where(*product_filters)
        if product_filters:
            matching_product_stmt = matching_product_stmt.where(product_text_match_condition)
        else:
            matching_product_stmt = matching_product_stmt.where(product_text_match_condition)

        direct_matching_product_ids = set(self.session.exec(matching_product_stmt).all())

        # 3. Query for Product IDs matching Attribute fields
        attr_text_match_condition = or_(
            ProductAttribute.raw_value.ilike(like_pattern),
            ProductAttribute.display_name.ilike(like_pattern),
            ProductAttribute.attribute_name.ilike(like_pattern),
        )

        attr_matching_stmt = select(ProductAttribute.product_id).where(attr_text_match_condition)
        attr_matching_product_ids = set(self.session.exec(attr_matching_stmt).all())

        # Candidate Product IDs pool
        all_candidate_ids = direct_matching_product_ids.union(attr_matching_product_ids)

        if not all_candidate_ids:
            return KeywordSearchResponse(query=raw_query, total=0, results=[])

        # 4. Fetch Candidate Products with filters applied
        final_products_stmt = select(Product).where(Product.id.in_(all_candidate_ids))
        if product_filters:
            final_products_stmt = final_products_stmt.where(*product_filters)

        candidate_products = self.session.exec(final_products_stmt).all()

        if not candidate_products:
            return KeywordSearchResponse(query=raw_query, total=0, results=[])

        candidate_product_ids = [p.id for p in candidate_products]

        # 5. Batch load attributes for candidate products to prevent N+1 queries
        attributes_stmt = select(ProductAttribute).where(ProductAttribute.product_id.in_(candidate_product_ids))
        all_candidate_attrs = self.session.exec(attributes_stmt).all()

        product_attrs_map: Dict[uuid.UUID, List[ProductAttribute]] = {}
        for attr in all_candidate_attrs:
            product_attrs_map.setdefault(attr.product_id, []).append(attr)

        # 6. Deterministic Score Calculation & Field Matching
        results: List[KeywordSearchResultItem] = []

        for p in candidate_products:
            matched_fields: List[str] = []
            field_scores: List[float] = []

            p_sku = (p.sku or "").strip()
            p_model = (p.model or "").strip()
            p_name = (p.product_name or "").strip()
            p_brand = (p.brand or "").strip()
            p_category = (p.category or "").strip()

            # Exact Matches
            if p_sku.lower() == query_lower:
                matched_fields.append("sku")
                field_scores.append(1.00)
            elif raw_query in p_sku or query_lower in p_sku.lower():
                matched_fields.append("sku")
                field_scores.append(0.80)

            if p_model and p_model.lower() == query_lower:
                matched_fields.append("model")
                field_scores.append(0.95)
            elif p_model and (raw_query in p_model or query_lower in p_model.lower()):
                if "model" not in matched_fields:
                    matched_fields.append("model")
                field_scores.append(0.75)

            if p_name.lower() == query_lower:
                matched_fields.append("product_name")
                field_scores.append(0.90)
            elif query_lower in p_name.lower():
                if "product_name" not in matched_fields:
                    matched_fields.append("product_name")
                field_scores.append(0.70)

            if p_brand.lower() == query_lower:
                matched_fields.append("brand")
                field_scores.append(0.85)
            elif query_lower in p_brand.lower():
                if "brand" not in matched_fields:
                    matched_fields.append("brand")
                field_scores.append(0.65)

            if query_lower in p_category.lower():
                matched_fields.append("category")
                field_scores.append(0.60)

            # Attribute Matches
            p_attrs = product_attrs_map.get(p.id, [])
            attr_matched = False
            for attr in p_attrs:
                r_val = (attr.raw_value or "").strip().lower()
                d_val = (attr.display_name or "").strip().lower()
                if query_lower in r_val or query_lower in d_val:
                    attr_matched = True
                    break

            if attr_matched:
                matched_fields.append("attributes")
                field_scores.append(0.55)

            if not field_scores:
                continue

            base_score = max(field_scores)
            multi_field_bonus = min(0.05, max(0, len(matched_fields) - 1) * 0.02)
            final_keyword_score = round(min(1.00, base_score + multi_field_bonus), 4)

            item = KeywordSearchResultItem(
                product_id=str(p.id),
                product_name=p.product_name,
                sku=p.sku,
                brand=p.brand,
                model=p.model,
                category=p.category,
                status=str(p.status.value if hasattr(p.status, "value") else p.status),
                quality_score=float(p.quality_score),
                keyword_score=final_keyword_score,
                matched_fields=matched_fields,
            )
            results.append(item)

        # 7. Sort by keyword_score DESC, quality_score DESC, updated_at DESC
        results.sort(key=lambda r: (r.keyword_score, r.quality_score), reverse=True)

        return KeywordSearchResponse(
            query=raw_query,
            total=len(results),
            results=results[:limit],
        )
