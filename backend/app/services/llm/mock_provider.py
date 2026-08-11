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
        Mock assistant response for automated tests.
        """
        msg_lower = (message or "").lower()
        page_ctx = (context or {}).get("page", "") if isinstance(context, dict) else ""

        if "upload" in msg_lower or page_ctx == "upload":
            return {
                "message": (
                    "To upload a document in CatalogIQ:\n"
                    "1. Navigate to the **Upload Page** (`/upload`).\n"
                    "2. Drag and drop your technical catalog PDF (up to 50MB).\n"
                    "3. Click **Start Ingestion**. CatalogIQ automatically parses, extracts, validates, enriches, and indexes the catalog items."
                ),
                "suggestions": [
                    "What happens after parsing?",
                    "Why is my document still processing?",
                    "How does extraction work?",
                ],
            }

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
                "CatalogIQ is an AI-powered Product Intelligence platform. "
                "I can help you understand document processing, extraction, validation quality scores, multi-source reconciliation, and hybrid search."
            ),
            "suggestions": [
                "How do I upload a catalog?",
                "How does search work?",
                "What does product quality score mean?",
            ],
        }


