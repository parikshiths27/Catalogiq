"""
MockProvider — deterministic LLM provider for automated tests.

IMPORTANT: This provider may ONLY be instantiated when settings.ENV == "test".
The factory (factory.py) enforces this restriction.

The mock returns a realistic, pre-baked ExtractionResult that matches
the MockParser's document output (Industrial Motor MX-500, SKU MX500-230).
This allows full pipeline integration tests without any external API calls.
"""
from typing import Any, Dict

from app.services.llm.base import BaseLLMProvider, ExtractionResult, RawAttributeItem, CommerceEnrichment
from app.services.llm.prompts import PROMPT_VERSION


class MockProvider(BaseLLMProvider):
    """
    Test-only provider returning a deterministic ExtractionResult.
    Mirrors the output that the real MockParser produces so pipeline
    integration tests are self-consistent.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    def extract(self, ir: Dict[str, Any]) -> ExtractionResult:
        """
        Returns a pre-baked result matching the MockParser's Industrial Motor IR.
        Includes both deterministic-style table attributes and LLM-style semantic fields.
        """
        return ExtractionResult(
            product_name="Industrial Motor MX-500",
            brand="TechMotors",
            sku="MX500-230",
            model_number="MX-500",
            category="Electric Motor",
            subcategory="AC Induction Motor",
            product_type="Three-phase",
            description=(
                "The TechMotors MX-500 is a three-phase AC induction motor rated at 5.5 kW "
                "for industrial applications requiring reliable continuous duty operation."
            ),
            attributes=[
                RawAttributeItem(
                    name="rated_voltage",
                    display_name="Rated Voltage",
                    raw_value="230 V",
                    unit="V",
                    data_type="numeric",
                    evidence_text="Voltage | 230 V",
                    page_number=2,
                    extraction_method="llm",
                    evidence_verified=False,  # pipeline sets this
                    llm_confidence=0.95,
                ),
                RawAttributeItem(
                    name="rated_power",
                    display_name="Rated Power",
                    raw_value="5.5 kW",
                    unit="kW",
                    data_type="numeric",
                    evidence_text="Power | 5.5 kW",
                    page_number=2,
                    extraction_method="llm",
                    evidence_verified=False,
                    llm_confidence=0.95,
                ),
                RawAttributeItem(
                    name="rated_speed",
                    display_name="Rated Speed",
                    raw_value="1440 RPM",
                    unit="RPM",
                    data_type="numeric",
                    evidence_text="Speed | 1440 RPM",
                    page_number=2,
                    extraction_method="llm",
                    evidence_verified=False,
                    llm_confidence=0.92,
                ),
                RawAttributeItem(
                    name="weight",
                    display_name="Weight",
                    raw_value="32 kg",
                    unit="kg",
                    data_type="numeric",
                    evidence_text="Weight | 32 kg",
                    page_number=2,
                    extraction_method="llm",
                    evidence_verified=False,
                    llm_confidence=0.90,
                ),
            ],
            features=[
                "Continuous duty rated",
                "IP55 protection class",
                "Class F insulation",
            ],
            applications=[
                "Industrial conveyor systems",
                "Pumping equipment",
                "General industrial machinery",
            ],
            certifications=["CE", "IP55"],
            keywords=["industrial motor", "AC motor", "three-phase", "induction motor"],
            provider_name="mock",
            model_name="mock-v1",
            prompt_version=PROMPT_VERSION,
        )

    def enrich(self, product_context: Dict[str, Any]) -> CommerceEnrichment:
        """
        Returns a deterministic CommerceEnrichment object for automated testing.
        """
        from app.services.llm.base import CommerceEnrichment
        from app.services.llm.prompts import ENRICHMENT_PROMPT_VERSION

        p_name = product_context.get("product_name", "Industrial Motor MX-500")
        brand = product_context.get("brand", "CatalogIQ")
        sku = product_context.get("sku", "MX500-230")

        return CommerceEnrichment(
            commerce_description=(
                f"The {p_name} from {brand} (SKU: {sku}) is a high-performance industrial motor "
                "designed for continuous duty B2B applications. Engineered with 5.5 kW rated power, "
                "230 V operating voltage, and 1440 RPM rated speed, it provides reliable industrial drive."
            ),
            short_description=f"{brand} {p_name} 5.5 kW 230 V industrial motor.",
            features=[
                "Continuous duty rated",
                "Class F insulation",
                "IP55 protection class",
            ],
            applications=[
                "Industrial conveyor systems",
                "Pumping equipment",
            ],
            keywords=[
                brand.lower(),
                sku.lower(),
                "industrial motor",
                "5.5 kw motor",
                "230v motor",
            ],
            seo_title=f"{brand} {p_name} - 5.5 kW B2B Industrial Motor ({sku})",
            seo_description=f"Buy the {brand} {p_name} ({sku}) - 5.5 kW, 230 V industrial motor with verified specification backing.",
            provider_name="mock",
            model_name="mock-v1",
            prompt_version=ENRICHMENT_PROMPT_VERSION,
            confidence=0.92,
        )

    def generate_assistant_response(
        self,
        message: str,
        history: Any = None,
        context: Any = None,
    ) -> Dict[str, Any]:
        """
        Mock assistant response for automated tests and grounded operational guidance.
        """
        msg_lower = (message or "").lower()
        ctx = context if isinstance(context, dict) else {}
        page_ctx = ctx.get("page", "")

        # 1. Product search not found
        product_search = ctx.get("product_search")
        if product_search and product_search.get("found") is False:
            queried_id = product_search.get("queried_identifier", "the requested product")
            return {
                "message": f"Product '{queried_id}' could not be found in the current CatalogIQ catalog database.",
                "suggestions": [
                    "Search for another SKU or part number",
                    "How do I upload a new catalog document?",
                    "What file formats are supported?",
                ],
            }

        # 2. Product-specific queries with retrieved product_facts
        product_facts = ctx.get("product_facts")
        if product_facts:
            sku = product_facts.get("sku", "Unknown SKU")
            name = product_facts.get("product_name", sku)
            brand = product_facts.get("brand", "Unknown Brand")
            status = product_facts.get("status", "unknown")
            quality_score = product_facts.get("quality_score", 0.0)
            open_issues = product_facts.get("open_validation_issues", [])
            attributes = product_facts.get("attributes", [])

            # A. Questions asking why product requires review or is in needs_review status
            if "review" in msg_lower or "needs_review" in msg_lower or "why" in msg_lower:
                issue_bullets = []
                for idx, issue in enumerate(open_issues, 1):
                    msg = issue.get("message", issue.get("validation_type", "Validation issue"))
                    sev = issue.get("severity", "warning").upper()
                    issue_bullets.append(f"{idx}. **[{sev}]**: {msg}")

                if not issue_bullets:
                    issue_bullets.append("1. Product status is marked for quality verification before catalog publication.")

                issues_text = "\n".join(issue_bullets)
                return {
                    "message": (
                        f"Product **{name}** (SKU: `{sku}`, Brand: {brand}) has a quality score of **{quality_score:.1f}%** "
                        f"and status `{status}`. It requires human review due to the following open validation issues:\n\n"
                        f"{issues_text}\n\n"
                        f"Reviewers can verify or override these values in the **Human Review Queue** (`/reviews`)."
                    ),
                    "suggestions": [
                        f"Where did the attributes for {sku} come from?",
                        "How do I resolve validation issues in Human Review?",
                        "What is the quality score threshold for verification?",
                    ],
                }

            # B. Questions asking about attribute evidence / provenance
            if "where" in msg_lower or "evidence" in msg_lower or "source" in msg_lower or "attribute" in msg_lower or "diameter" in msg_lower:
                # Find matching attribute
                matched_attr = None
                for attr in attributes:
                    a_name = (attr.get("name") or "").lower()
                    a_disp = (attr.get("display_name") or "").lower()
                    if any(term in msg_lower for term in [a_name, a_disp]) and (a_name or a_disp):
                        matched_attr = attr
                        break
                if not matched_attr and attributes:
                    matched_attr = attributes[0]

                if matched_attr:
                    aname = matched_attr.get("display_name") or matched_attr.get("name")
                    val = matched_attr.get("raw_value")
                    ev = matched_attr.get("evidence") or {}
                    src_name = ev.get("source_name", "Catalog Document")
                    page_num = ev.get("page_number", 1)
                    ev_text = ev.get("evidence_text", f"{aname}: {val}")
                    conf = matched_attr.get("confidence", 0.95)

                    return {
                        "message": (
                            f"The **{aname}** attribute for **{name}** (`{val}`) was extracted from **{src_name}** "
                            f"(Page {page_num}) with **{conf * 100:.0f}% confidence**.\n\n"
                            f"**Source Document Evidence Quote**:\n"
                            f"> \"{ev_text}\""
                        ),
                        "suggestions": [
                            f"Why would product {sku} require human review?",
                            f"What other attributes were extracted for {sku}?",
                            "How does CatalogIQ verify evidence citations?",
                        ],
                    }

        # 3. Multi-source reconciliation questions
        if "reconcil" in msg_lower or "conflict" in msg_lower or "claim" in msg_lower:
            return {
                "message": (
                    "CatalogIQ reconciles conflicting manufacturer claims through an automated multi-source pipeline:\n\n"
                    "1. **Multi-Source Ingestion**: Ingests multiple technical documents, spec sheets, and distributor catalogs per product.\n"
                    "2. **Weighted Trust Hierarchy**: Applies higher confidence weighting to primary OEM manufacturer datasheets over distributor catalogs and secondary web sources.\n"
                    "3. **Verbatim Evidence Grounding**: Extracts bounding text citations and page numbers for every attribute claim.\n"
                    "4. **Conflict Detection & Human Review**: When sources provide contradictory values (e.g. differing voltages or dimensions), CatalogIQ records both competing claims, marks the product `needs_review`, and routes the discrepancy to the **Human Review Queue** (`/reviews`) for expert resolution."
                ),
                "suggestions": [
                    "What does needs_review mean?",
                    "How do I resolve a cross-source conflict in Human Review?",
                    "What happens when I upload a new catalog version?",
                ],
            }

        # 4. Upload & Ingestion questions
        if "upload" in msg_lower or page_ctx == "upload":
            return {
                "message": (
                    "To upload documents in CatalogIQ:\n"
                    "1. Navigate to the **Upload Page** (`/upload`).\n"
                    "2. Drag and drop your technical catalog documents (PDF, DOCX, XLSX, CSV, TXT, JSON, XML, HTML, MD, or ZIP up to 50MB per file).\n"
                    "3. Click **Start Ingestion**. CatalogIQ automatically parses multi-format files into a common Intermediate Representation (IR), extracts attributes, validates quality, enriches commerce descriptions, and indexes catalog items."
                ),
                "suggestions": [
                    "What file formats are supported?",
                    "How does batch processing work?",
                    "If I upload an Excel file, what happens?",
                ],
            }

        # 5. Search questions
        if "search" in msg_lower or page_ctx == "search":
            return {
                "message": (
                    "CatalogIQ Search operates in three modes:\n"
                    "1. **Hybrid Search** (Default): Combines PostgreSQL lexical keyword search with Qdrant vector semantic search.\n"
                    "2. **Semantic Search**: Vector similarity search using FastEmbed (`BAAI/bge-small-en-v1.5`).\n"
                    "3. **Keyword Search**: Exact and substring PostgreSQL matching on SKU, model, name, and attributes."
                ),
                "suggestions": [
                    "What does the relevance score mean?",
                    "What are exact match priorities?",
                    "How do facet filters work?",
                ],
            }

        return {
            "message": (
                "CatalogIQ is an AI-powered Product Intelligence and Enrichment platform. "
                "I can help you understand multi-format document processing, batch ingestion, attribute extraction, "
                "validation quality scores, product content enrichment, multi-source reconciliation, and hybrid search."
            ),
            "suggestions": [
                "What file formats are supported?",
                "How does batch processing work?",
                "What is product enrichment?",
            ],
        }


