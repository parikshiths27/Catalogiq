"""
CatalogIQ Enrichment Foundation Service Package.
Phase 11 Hackathon Product Content Enrichment.
"""
from app.services.enrichment.reference_loader import ReferenceDataLoader, get_reference_loader
from app.services.enrichment.normalizers import (
    PlaceholderCleaner,
    FractionNormalizer,
    UOMNormalizer,
    ManufacturerBrandNormalizer,
)
from app.services.enrichment.taxonomy import TaxonomyClassifier
from app.services.enrichment.attributes import AttributeExtractor
from app.services.enrichment.description_builder import DescriptionBuilder
from app.services.enrichment.validator import DeterministicValidator
from app.services.enrichment.evidence import EvidenceTracker

__all__ = [
    "ReferenceDataLoader",
    "get_reference_loader",
    "PlaceholderCleaner",
    "FractionNormalizer",
    "UOMNormalizer",
    "ManufacturerBrandNormalizer",
    "TaxonomyClassifier",
    "AttributeExtractor",
    "DescriptionBuilder",
    "DeterministicValidator",
    "EvidenceTracker",
]
