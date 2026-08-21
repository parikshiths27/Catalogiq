"""
Taxonomy Classification Service for CatalogIQ Enrichment Foundation.

Resolves:
- Dept
- Class
- Fine
- Classpath
- Product Name
Using candidate scoring and validation against authoritative reference taxonomy schemas.
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader
from app.services.enrichment.normalizers import PlaceholderCleaner


class TaxonomyClassifier:
    """Classifies catalog records into authoritative hierarchical taxonomies."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()

    def classify(
        self,
        part_desc: Optional[str],
        mfg_part_num: Optional[str] = None,
        canonical_brand: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classifies product into standard Dept/Class/Fine/Classpath.
        Returns:
            - dept: str
            - class_: str
            - fine: str
            - classpath: str
            - product_name: str
            - confidence: float
            - evidence: str
            - needs_review: bool
        """
        clean_desc = PlaceholderCleaner.clean_text_segment(part_desc or "")
        desc_lower = clean_desc.lower()
        mpn_lower = (mfg_part_num or "").lower()

        best_match: Optional[Dict[str, Any]] = None
        highest_score = 0
        matching_keywords: List[str] = []

        for entry in self.loader.taxonomies:
            score = 0
            matched_kws = []
            for kw in entry["keywords"]:
                pattern = rf"\b{re.escape(kw.lower())}\b"
                if re.search(pattern, desc_lower) or kw.lower() in mpn_lower:
                    # Multi-word keywords get higher weight
                    weight = len(kw.split()) * 2 + 1
                    score += weight
                    matched_kws.append(kw)

            if score > highest_score:
                highest_score = score
                best_match = entry
                matching_keywords = matched_kws

        if best_match and highest_score >= 1:
            confidence = min(0.95, 0.70 + (highest_score * 0.05))
            evidence = f"matched taxonomy keywords: {', '.join(matching_keywords)} -> {best_match['classpath']}"
            return {
                "dept": best_match["dept"],
                "class_": best_match["class_"],
                "fine": best_match["fine"],
                "classpath": best_match["classpath"],
                "product_name": best_match["product_name"],
                "confidence": round(confidence, 2),
                "evidence": evidence,
                "needs_review": False,
            }

        # Fallback for unclassified items
        return {
            "dept": "General Industrial",
            "class_": "Supplies",
            "fine": "Uncategorized",
            "classpath": "Industrial Supplies & MRO>General Supplies>Miscellaneous",
            "product_name": "Industrial Product",
            "confidence": 0.40,
            "evidence": "no definitive taxonomy match found; assigned fallback classpath",
            "needs_review": True,
        }
