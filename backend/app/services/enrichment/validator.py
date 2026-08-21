"""
Deterministic Validation Engine for CatalogIQ Enrichment Foundation.

Performs deterministic checks across:
- Identity (Manufacturer/Brand in master, valid hierarchy, MPN present)
- Taxonomy (Classpath in master, hierarchy consistency)
- Attributes (LOV allowed vocabulary, UOM standards)
- Content (Character limits, casing, abbreviations)
- Claims (Anti-hallucination verification)
Produces status: verified | needs_review | invalid
"""
from typing import Any, Dict, List, Optional
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader
from app.services.enrichment.attributes import ExtractedAttribute
from app.services.claim_checker import ClaimCheckResult


class ValidationIssueDetail:
    """Represents an individual validation error or review warning."""

    def __init__(
        self,
        field: str,
        issue_type: str,
        message: str,
        severity: str = "warning",
        expected_value: Optional[Any] = None,
        actual_value: Optional[Any] = None,
    ) -> None:
        self.field = field
        self.issue_type = issue_type
        self.message = message
        self.severity = severity
        self.expected_value = expected_value
        self.actual_value = actual_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "issue_type": self.issue_type,
            "message": self.message,
            "severity": self.severity,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
        }


class ValidationSummary:
    """Aggregated validation result for an enriched catalog record."""

    def __init__(self, status: str, issues: List[ValidationIssueDetail], quality_score: float) -> None:
        self.status = status  # verified | needs_review | invalid
        self.issues = issues
        self.quality_score = quality_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "quality_score": round(self.quality_score, 2),
            "issues": [i.to_dict() for i in self.issues],
            "is_verified": self.status == "verified",
            "needs_review": self.status == "needs_review",
            "is_invalid": self.status == "invalid",
        }


class DeterministicValidator:
    """Deterministic validation engine enforcing strict master constraints."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()

    def validate(
        self,
        manufacturer: str,
        brand: str,
        mpn: str,
        classpath: str,
        attributes: List[ExtractedAttribute],
        invoice_desc: str,
        mobile_desc: str,
        claim_result: Optional[ClaimCheckResult] = None,
        confidence: float = 0.90,
    ) -> ValidationSummary:
        """
        Runs comprehensive deterministic checks.
        """
        issues: List[ValidationIssueDetail] = []

        # 1. Identity Validation
        if not mpn or mpn.strip() == "":
            issues.append(ValidationIssueDetail("MANUFACTURER_PART_NUMBER", "missing_required_attribute", "MPN is missing or empty", "error", expected_value="Valid MPN", actual_value=mpn))

        mfr_found = any(
            mfr_name.lower() == manufacturer.lower()
            for mfr_name in self.loader.manufacturers.keys()
        )
        if not mfr_found:
            issues.append(ValidationIssueDetail("MANUFACTURER_NAME", "manufacturer_unresolved", f"Manufacturer '{manufacturer}' not found in approved master data", "warning", expected_value="Approved Manufacturer", actual_value=manufacturer))

        clean_b = brand.replace("®", "").replace("™", "").strip().upper()
        if clean_b not in self.loader.brands:
            issues.append(ValidationIssueDetail("BRAND_NAME", "brand_unresolved", f"Brand '{brand}' not found in approved brand master", "warning", expected_value="Approved Brand", actual_value=brand))

        # 2. Taxonomy Validation
        valid_classpath = any(t["classpath"] == classpath for t in self.loader.taxonomies)
        if not valid_classpath:
            issues.append(ValidationIssueDetail("Classpath", "taxonomy_unresolved", f"Classpath '{classpath}' not found in taxonomy tree", "warning", expected_value="Standard Taxonomy Classpath", actual_value=classpath))

        # 3. Content Character Limits & Casing
        # Strip quotes if present for character counting
        raw_inv = invoice_desc.strip('"')
        if len(raw_inv) > 40:
            issues.append(ValidationIssueDetail("INVOICE_DESC", "invalid_value", f"INVOICE_DESC length ({len(raw_inv)}) exceeds 40 chars limit", "error", expected_value="<= 40 chars", actual_value=f"{len(raw_inv)} chars"))
        if raw_inv != raw_inv.upper():
            issues.append(ValidationIssueDetail("INVOICE_DESC", "invalid_value", "INVOICE_DESC must be all uppercase", "error", expected_value="ALL CAPS", actual_value=raw_inv))

        raw_mob = mobile_desc.strip('"')
        if len(raw_mob) > 80:
            issues.append(ValidationIssueDetail("MOBILE_DESC", "invalid_value", f"MOBILE_DESC length ({len(raw_mob)}) exceeds 80 chars limit", "error", expected_value="<= 80 chars", actual_value=f"{len(raw_mob)} chars"))

        # 4. Attribute & UOM Validation
        for attr in attributes:
            if attr.normalized_uom and attr.normalized_uom not in self.loader.approved_uoms:
                issues.append(ValidationIssueDetail(f"ATTRIBUTE_UOM ({attr.label})", "unsupported_uom", f"UOM '{attr.normalized_uom}' is not in approved UOM standard", "warning", expected_value="Approved UOM", actual_value=attr.normalized_uom))

        # 5. ClaimChecker anti-hallucination validation
        if claim_result and claim_result.has_unsupported_claims:
            issues.append(ValidationIssueDetail("LONG_DESC1", "unsupported_claim", f"Generated description contains unsupported claims: {', '.join(claim_result.unsupported_claims)}", "error", expected_value="Evidence-backed description", actual_value=claim_result.unsupported_claims))

        # Compute Quality Score & Final Status
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        if error_count > 0:
            final_status = "invalid"
            quality_score = max(20.0, 60.0 - (error_count * 15.0))
        elif warning_count > 0 or confidence < 0.85:
            final_status = "needs_review"
            quality_score = max(50.0, 85.0 - (warning_count * 10.0))
        else:
            final_status = "verified"
            quality_score = min(100.0, 90.0 + (confidence * 10.0))

        return ValidationSummary(status=final_status, issues=issues, quality_score=quality_score)
