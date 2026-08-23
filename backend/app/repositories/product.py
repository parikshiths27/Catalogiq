import uuid
from typing import Optional, List
from sqlmodel import Session, select, and_
from app.models import Product, ProductStatus, ProductListItem, ProductAttribute, ValidationResult, ProductVersion, DuplicateCandidate

class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        return self.session.get(Product, product_id)

    def get_by_sku_brand(self, sku: str, brand: str) -> Optional[Product]:
        statement = select(Product).where(and_(Product.sku == sku, Product.brand == brand))
        return self.session.exec(statement).first()

    def list_catalog_items(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
        quality_score_min: Optional[float] = None,
        quality_score_max: Optional[float] = None,
    ) -> List[ProductListItem]:
        statement = select(
            Product.id,
            Product.product_name,
            Product.brand,
            Product.sku,
            Product.category,
            Product.status,
            Product.quality_score,
            Product.updated_at,
        )
        conditions = []
        if status:
            conditions.append(Product.status == status)
        if brand:
            conditions.append(Product.brand == brand)
        if category:
            conditions.append(Product.category == category)
        if quality_score_min is not None:
            conditions.append(Product.quality_score >= quality_score_min)
        if quality_score_max is not None:
            conditions.append(Product.quality_score <= quality_score_max)
        if conditions:
            statement = statement.where(and_(*conditions))
        statement = statement.order_by(Product.updated_at.desc()).offset(offset).limit(limit)
        rows = self.session.exec(statement).all()
        return [
            ProductListItem(
                id=r[0],
                product_name=r[1],
                brand=r[2],
                sku=r[3],
                category=r[4],
                status=r[5].value if hasattr(r[5], "value") else str(r[5]),
                quality_score=float(r[6]),
                updated_at=r[7],
            )
            for r in rows
        ]

    def list_products(
        self, 
        limit: int = 100, 
        offset: int = 0, 
        status: Optional[str] = None, 
        brand: Optional[str] = None,
        category: Optional[str] = None,
        quality_score_min: Optional[float] = None,
        quality_score_max: Optional[float] = None,
    ) -> List[Product]:
        statement = select(Product)
        conditions = []
        if status:
            conditions.append(Product.status == status)
        if brand:
            conditions.append(Product.brand == brand)
        if category:
            conditions.append(Product.category == category)
        if quality_score_min is not None:
            conditions.append(Product.quality_score >= quality_score_min)
        if quality_score_max is not None:
            conditions.append(Product.quality_score <= quality_score_max)
        if conditions:
            statement = statement.where(and_(*conditions))
        statement = statement.offset(offset).limit(limit)
        return list(self.session.exec(statement).all())

    def create(self, product: Product) -> Product:
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)
        return product

    def save(self, product: Product) -> Product:
        self.session.add(product)
        self.session.commit()
        self.session.refresh(product)
        return product

    def get_attributes(self, product_id: uuid.UUID) -> List[ProductAttribute]:
        statement = select(ProductAttribute).where(ProductAttribute.product_id == product_id)
        return list(self.session.exec(statement).all())

    def get_validations(self, product_id: uuid.UUID, status: Optional[str] = None) -> List[ValidationResult]:
        statement = select(ValidationResult).where(ValidationResult.product_id == product_id)
        if status:
            statement = statement.where(ValidationResult.status == status)
        return list(self.session.exec(statement).all())

    def get_versions(self, product_id: uuid.UUID) -> List[ProductVersion]:
        statement = select(ProductVersion).where(ProductVersion.product_id == product_id).order_by(ProductVersion.version_number.desc())
        return list(self.session.exec(statement).all())

    def get_duplicates(self, product_id: uuid.UUID, status: Optional[str] = None) -> List[DuplicateCandidate]:
        statement = select(DuplicateCandidate).where(
            (DuplicateCandidate.product_id == product_id) | (DuplicateCandidate.candidate_product_id == product_id)
        )
        if status:
            statement = statement.where(DuplicateCandidate.status == status)
        return list(self.session.exec(statement).all())
