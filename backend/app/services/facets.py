"""
Facet Aggregation Service for CatalogIQ.
Provides high-performance, disjunctive facet aggregation using PostgreSQL GROUP BY
queries for categories, brands, subcategories, status, quality score ranges, and dynamic attributes.
"""
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_, and_

from app.models import Product, ProductAttribute, AttributeStatus
from app.services.keyword_search import KeywordSearchService

logger = logging.getLogger(__name__)


def parse_list_param(val: Any) -> List[str]:
    """Helper to parse scalar strings, lists, or comma-separated filter parameters."""
    if not val:
        return []
    if isinstance(val, list):
        return [s.strip() for s in val if isinstance(s, str) and s.strip()]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


class FacetCountItem(BaseModel):
    value: str
    count: int


class QualityScoreRangeItem(BaseModel):
    label: str
    min: float
    max: float
    count: int


class DynamicAttributeFacet(BaseModel):
    attribute_name: str
    display_name: str
    data_type: str
    values: List[FacetCountItem] = Field(default_factory=list)


class FacetResponsePayload(BaseModel):
    categories: List[FacetCountItem] = Field(default_factory=list)
    brands: List[FacetCountItem] = Field(default_factory=list)
    subcategories: List[FacetCountItem] = Field(default_factory=list)
    statuses: List[FacetCountItem] = Field(default_factory=list)
    quality_score_ranges: List[QualityScoreRangeItem] = Field(default_factory=list)
    attributes: List[DynamicAttributeFacet] = Field(default_factory=list)


class FacetSearchResponse(BaseModel):
    query: str
    facets: FacetResponsePayload


class FacetAggregationService:
    """
    Read-only facet aggregation service supporting disjunctive faceting and
    safe dynamic attribute counting.
    """

    def __init__(self, session: Session):
        self.session = session

    def _get_matching_product_ids_for_query(self, raw_query: Optional[str]) -> Optional[List[Any]]:
        """Returns list of Product IDs matching raw search query string if query is present."""
        if not raw_query or not raw_query.strip():
            return None

        q = raw_query.strip()
        like_pattern = f"%{q}%"

        # Product fields match
        prod_stmt = select(Product.id).where(
            or_(
                Product.sku.ilike(like_pattern),
                Product.model.ilike(like_pattern),
                Product.product_name.ilike(like_pattern),
                Product.brand.ilike(like_pattern),
                Product.category.ilike(like_pattern),
            )
        )
        prod_ids = set(self.session.exec(prod_stmt).all())

        # Attribute raw_value / display_name match
        attr_stmt = select(ProductAttribute.product_id).where(
            or_(
                ProductAttribute.raw_value.ilike(like_pattern),
                ProductAttribute.display_name.ilike(like_pattern),
                ProductAttribute.attribute_name.ilike(like_pattern),
            )
        )
        attr_ids = set(self.session.exec(attr_stmt).all())

        return list(prod_ids.union(attr_ids))

    def _build_filter_conditions(
        self,
        matching_ids: Optional[List[Any]],
        category_list: List[str],
        brand_list: List[str],
        subcategory_list: List[str],
        status_list: List[str],
        min_quality: Optional[float],
        max_quality: Optional[float],
        exclude_facet: Optional[str] = None,
    ) -> List[Any]:
        """Constructs SQL filters applying query match and all active filters except exclude_facet."""
        conds = []

        if matching_ids is not None:
            conds.append(Product.id.in_(matching_ids))

        if exclude_facet != "category" and category_list:
            conds.append(func.lower(Product.category).in_([c.lower() for c in category_list]))

        if exclude_facet != "brand" and brand_list:
            conds.append(func.lower(Product.brand).in_([b.lower() for b in brand_list]))

        if exclude_facet != "subcategory" and subcategory_list:
            conds.append(func.lower(Product.subcategory).in_([sc.lower() for sc in subcategory_list]))

        if exclude_facet != "status" and status_list:
            conds.append(func.lower(Product.status).in_([s.lower() for s in status_list]))

        if exclude_facet != "quality" and min_quality is not None:
            conds.append(Product.quality_score >= float(min_quality))

        if exclude_facet != "quality" and max_quality is not None:
            conds.append(Product.quality_score <= float(max_quality))

        return conds

    def compute_facets(
        self,
        query: Optional[str] = None,
        category: Any = None,
        brand: Any = None,
        subcategory: Any = None,
        product_status: Any = None,
        min_quality_score: Optional[float] = None,
        max_quality_score: Optional[float] = None,
    ) -> FacetResponsePayload:
        """
        Computes disjunctive facet counts using PostgreSQL GROUP BY aggregations.
        """
        category_list = parse_list_param(category)
        brand_list = parse_list_param(brand)
        subcategory_list = parse_list_param(subcategory)
        status_list = parse_list_param(product_status)

        matching_ids = self._get_matching_product_ids_for_query(query)

        # 1. Categories Facet (Disjunctive: ignores category filter)
        cat_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="category"
        )
        cat_stmt = select(Product.category, func.count(Product.id)).where(*cat_conds).group_by(Product.category)
        cat_rows = self.session.exec(cat_stmt).all()
        categories = [FacetCountItem(value=row[0], count=row[1]) for row in cat_rows if row[0]]
        categories.sort(key=lambda x: x.count, reverse=True)

        # 2. Brands Facet (Disjunctive: ignores brand filter)
        brand_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="brand"
        )
        brand_stmt = select(Product.brand, func.count(Product.id)).where(*brand_conds).group_by(Product.brand)
        brand_rows = self.session.exec(brand_stmt).all()
        brands = [FacetCountItem(value=row[0], count=row[1]) for row in brand_rows if row[0]]
        brands.sort(key=lambda x: x.count, reverse=True)

        # 3. Subcategories Facet (Disjunctive: ignores subcategory filter)
        subcat_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="subcategory"
        )
        subcat_stmt = select(Product.subcategory, func.count(Product.id)).where(Product.subcategory.isnot(None), *subcat_conds).group_by(Product.subcategory)
        subcat_rows = self.session.exec(subcat_stmt).all()
        subcategories = [FacetCountItem(value=row[0], count=row[1]) for row in subcat_rows if row[0]]
        subcategories.sort(key=lambda x: x.count, reverse=True)

        # 4. Statuses Facet (Disjunctive: ignores status filter)
        status_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="status"
        )
        status_stmt = select(Product.status, func.count(Product.id)).where(*status_conds).group_by(Product.status)
        status_rows = self.session.exec(status_stmt).all()
        statuses = [
            FacetCountItem(
                value=row[0].value if hasattr(row[0], "value") else str(row[0]),
                count=row[1]
            )
            for row in status_rows if row[0]
        ]
        statuses.sort(key=lambda x: x.count, reverse=True)

        # 5. Quality Score Ranges Facet (Disjunctive: ignores quality score filter)
        qual_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="quality"
        )
        qual_products = self.session.exec(select(Product.quality_score).where(*qual_conds)).all()

        r1 = sum(1 for q in qual_products if q >= 90.0)
        r2 = sum(1 for q in qual_products if 80.0 <= q < 90.0)
        r3 = sum(1 for q in qual_products if 70.0 <= q < 80.0)
        r4 = sum(1 for q in qual_products if q < 70.0)

        quality_ranges = [
            QualityScoreRangeItem(label="90-100 Excellent", min=90.0, max=100.0, count=r1),
            QualityScoreRangeItem(label="80-89 Good", min=80.0, max=89.99, count=r2),
            QualityScoreRangeItem(label="70-79 Fair", min=70.0, max=79.99, count=r3),
            QualityScoreRangeItem(label="< 70 Needs Review", min=0.0, max=69.99, count=r4),
        ]

        # 6. Dynamic Attributes Facets (Top 5 attributes with max 20 values)
        all_conds = self._build_filter_conditions(
            matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet=None
        )
        ctx_prod_ids = self.session.exec(select(Product.id).where(*all_conds)).all()

        dynamic_attribute_facets: List[DynamicAttributeFacet] = []
        if ctx_prod_ids:
            # Find top 5 most frequent attribute names for context products
            top_attrs_stmt = (
                select(ProductAttribute.attribute_name, ProductAttribute.display_name, ProductAttribute.data_type, func.count(ProductAttribute.id))
                .where(
                    ProductAttribute.product_id.in_(ctx_prod_ids),
                    ProductAttribute.confidence >= 0.70,
                    ProductAttribute.status != AttributeStatus.missing,
                )
                .group_by(ProductAttribute.attribute_name, ProductAttribute.display_name, ProductAttribute.data_type)
                .order_by(func.count(ProductAttribute.id).desc())
                .limit(5)
            )
            top_attrs = self.session.exec(top_attrs_stmt).all()

            for attr_name, disp_name, data_type, _ in top_attrs:
                # Count raw values for this attribute
                val_stmt = (
                    select(ProductAttribute.raw_value, func.count(ProductAttribute.id))
                    .where(
                        ProductAttribute.product_id.in_(ctx_prod_ids),
                        ProductAttribute.attribute_name == attr_name,
                        ProductAttribute.confidence >= 0.70,
                        ProductAttribute.status != AttributeStatus.missing,
                    )
                    .group_by(ProductAttribute.raw_value)
                    .order_by(func.count(ProductAttribute.id).desc())
                    .limit(20)
                )
                val_rows = self.session.exec(val_stmt).all()
                val_items = [FacetCountItem(value=r[0], count=r[1]) for r in val_rows if r[0]]
                if val_items:
                    dynamic_attribute_facets.append(
                        DynamicAttributeFacet(
                            attribute_name=attr_name,
                            display_name=disp_name or attr_name,
                            data_type=str(data_type.value if hasattr(data_type, "value") else data_type),
                            values=val_items,
                        )
                    )

        return FacetResponsePayload(
            categories=categories,
            brands=brands,
            subcategories=subcategories,
            statuses=statuses,
            quality_score_ranges=quality_ranges,
            attributes=dynamic_attribute_facets,
        )
