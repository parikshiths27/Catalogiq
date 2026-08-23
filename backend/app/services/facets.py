"""
Facet Aggregation Service for CatalogIQ.
Provides high-performance, disjunctive facet aggregation using PostgreSQL GROUP BY
queries for categories, brands, subcategories, status, quality score ranges, and dynamic attributes.
"""
import logging
import concurrent.futures
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_, and_
from sqlalchemy import case

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

        import concurrent.futures
        from sqlalchemy import case
        from app.db.session import engine

        bind = self.session.get_bind()
        is_sqlite = bind.dialect.name == "sqlite"

        # 1. Categories Facet
        def run_categories(s: Session):
            cat_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="category"
            )
            cat_stmt = select(Product.category, func.count(Product.id)).where(*cat_conds).group_by(Product.category)
            cat_rows = s.exec(cat_stmt).all()
            cats = [FacetCountItem(value=row[0], count=row[1]) for row in cat_rows if row[0]]
            cats.sort(key=lambda x: x.count, reverse=True)
            return cats

        # 2. Brands Facet
        def run_brands(s: Session):
            brand_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="brand"
            )
            brand_stmt = select(Product.brand, func.count(Product.id)).where(*brand_conds).group_by(Product.brand)
            brand_rows = s.exec(brand_stmt).all()
            brs = [FacetCountItem(value=row[0], count=row[1]) for row in brand_rows if row[0]]
            brs.sort(key=lambda x: x.count, reverse=True)
            return brs

        # 3. Subcategories Facet
        def run_subcategories(s: Session):
            subcat_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="subcategory"
            )
            subcat_stmt = select(Product.subcategory, func.count(Product.id)).where(Product.subcategory.isnot(None), *subcat_conds).group_by(Product.subcategory)
            subcat_rows = s.exec(subcat_stmt).all()
            subcats = [FacetCountItem(value=row[0], count=row[1]) for row in subcat_rows if row[0]]
            subcats.sort(key=lambda x: x.count, reverse=True)
            return subcats

        # 4. Statuses Facet
        def run_statuses(s: Session):
            status_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="status"
            )
            status_stmt = select(Product.status, func.count(Product.id)).where(*status_conds).group_by(Product.status)
            status_rows = s.exec(status_stmt).all()
            stats = [
                FacetCountItem(
                    value=row[0].value if hasattr(row[0], "value") else str(row[0]),
                    count=row[1]
                )
                for row in status_rows if row[0]
            ]
            stats.sort(key=lambda x: x.count, reverse=True)
            return stats

        # 5. Quality Score Ranges (SQL Case Aggregation)
        def run_quality_ranges(s: Session):
            qual_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet="quality"
            )
            qual_row = s.exec(
                select(
                    func.coalesce(func.sum(case((Product.quality_score >= 90.0, 1), else_=0)), 0),
                    func.coalesce(func.sum(case((and_(Product.quality_score >= 80.0, Product.quality_score < 90.0), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((and_(Product.quality_score >= 70.0, Product.quality_score < 80.0), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((Product.quality_score < 70.0, 1), else_=0)), 0),
                ).where(*qual_conds)
            ).first()
            r1 = int(qual_row[0] or 0) if qual_row else 0
            r2 = int(qual_row[1] or 0) if qual_row else 0
            r3 = int(qual_row[2] or 0) if qual_row else 0
            r4 = int(qual_row[3] or 0) if qual_row else 0

            return [
                QualityScoreRangeItem(label="90-100 Excellent", min=90.0, max=100.0, count=r1),
                QualityScoreRangeItem(label="80-89 Good", min=80.0, max=89.99, count=r2),
                QualityScoreRangeItem(label="70-79 Fair", min=70.0, max=79.99, count=r3),
                QualityScoreRangeItem(label="< 70 Needs Review", min=0.0, max=69.99, count=r4),
            ]

        # 6. Dynamic Attributes Facets (Single batched group-by query)
        def run_dynamic_attributes(s: Session):
            all_conds = self._build_filter_conditions(
                matching_ids, category_list, brand_list, subcategory_list, status_list, min_quality_score, max_quality_score, exclude_facet=None
            )
            ctx_prod_ids = s.exec(select(Product.id).where(*all_conds)).all()
            if not ctx_prod_ids:
                return []

            # Find top 5 most frequent attribute names
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
            top_attrs = s.exec(top_attrs_stmt).all()
            if not top_attrs:
                return []

            top_names = [r[0] for r in top_attrs]
            attr_meta = {r[0]: (r[1], r[2]) for r in top_attrs}

            # Single batched query for values of all top attributes
            val_stmt = (
                select(ProductAttribute.attribute_name, ProductAttribute.raw_value, func.count(ProductAttribute.id))
                .where(
                    ProductAttribute.product_id.in_(ctx_prod_ids),
                    ProductAttribute.attribute_name.in_(top_names),
                    ProductAttribute.confidence >= 0.70,
                    ProductAttribute.status != AttributeStatus.missing,
                )
                .group_by(ProductAttribute.attribute_name, ProductAttribute.raw_value)
                .order_by(func.count(ProductAttribute.id).desc())
            )
            val_rows = s.exec(val_stmt).all()

            # Group values by attribute_name
            attr_values_map: Dict[str, List[FacetCountItem]] = {}
            for attr_name, raw_val, cnt in val_rows:
                if raw_val:
                    cur_list = attr_values_map.setdefault(attr_name, [])
                    if len(cur_list) < 20:
                        cur_list.append(FacetCountItem(value=raw_val, count=cnt))

            facets_list = []
            for attr_name in top_names:
                disp_name, data_type = attr_meta[attr_name]
                v_items = attr_values_map.get(attr_name, [])
                if v_items:
                    facets_list.append(
                        DynamicAttributeFacet(
                            attribute_name=attr_name,
                            display_name=disp_name or attr_name,
                            data_type=str(data_type.value if hasattr(data_type, "value") else data_type),
                            values=v_items,
                        )
                    )
            return facets_list

        if is_sqlite:
            categories = run_categories(self.session)
            brands = run_brands(self.session)
            subcategories = run_subcategories(self.session)
            statuses = run_statuses(self.session)
            quality_ranges = run_quality_ranges(self.session)
            dynamic_attribute_facets = run_dynamic_attributes(self.session)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                def exec_with_session(fn):
                    with Session(bind) as s:
                        return fn(s)

                f_cats = executor.submit(lambda: exec_with_session(run_categories))
                f_brands = executor.submit(lambda: exec_with_session(run_brands))
                f_subcats = executor.submit(lambda: exec_with_session(run_subcategories))
                f_stats = executor.submit(lambda: exec_with_session(run_statuses))
                f_qual = executor.submit(lambda: exec_with_session(run_quality_ranges))
                f_dyn = executor.submit(lambda: exec_with_session(run_dynamic_attributes))

                categories = f_cats.result()
                brands = f_brands.result()
                subcategories = f_subcats.result()
                statuses = f_stats.result()
                quality_ranges = f_qual.result()
                dynamic_attribute_facets = f_dyn.result()

        return FacetResponsePayload(
            categories=categories,
            brands=brands,
            subcategories=subcategories,
            statuses=statuses,
            quality_score_ranges=quality_ranges,
            attributes=dynamic_attribute_facets,
        )
