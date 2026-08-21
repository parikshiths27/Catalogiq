"""
Evidence and Provenance Tracking Service for CatalogIQ Enrichment Foundation.

Stores field-level provenance:
- field
- value
- source
- evidence
- confidence
"""
from typing import Any, Dict, List, Optional


class FieldEvidence:
    """Individual field provenance item."""

    def __init__(
        self,
        field: str,
        value: Any,
        source: str,
        evidence: str,
        confidence: float,
    ) -> None:
        self.field = field
        self.value = value
        self.source = source
        self.evidence = evidence
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "source": self.source,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
        }


class EvidenceTracker:
    """Collects and organizes traceable provenance records for enriched records."""

    def __init__(self) -> None:
        self.records: List[FieldEvidence] = []

    def add(
        self,
        field: str,
        value: Any,
        source: str,
        evidence: str,
        confidence: float,
    ) -> None:
        """Records provenance for an enriched field."""
        if value is not None and value != "":
            self.records.append(FieldEvidence(
                field=field,
                value=value,
                source=source,
                evidence=evidence,
                confidence=confidence,
            ))

    def get_summary(self) -> Dict[str, Any]:
        """Returns aggregated provenance report and overall confidence score."""
        if not self.records:
            return {"overall_confidence": 0.0, "total_fields_tracked": 0, "evidence": []}

        avg_conf = sum(r.confidence for r in self.records) / len(self.records)
        return {
            "overall_confidence": round(avg_conf, 2),
            "total_fields_tracked": len(self.records),
            "evidence": [r.to_dict() for r in self.records],
        }
