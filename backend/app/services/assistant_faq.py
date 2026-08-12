"""
CatalogIQ Assistant Fast-Path FAQ Engine.
Provides conservative, deterministic fast-path responses for high-confidence common questions
grounded strictly in docs/ASSISTANT_MANUAL.md and CATALOGIQ_ASSISTANT_SYSTEM_PROMPT.
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FAQ_ENTRIES: List[Dict[str, Any]] = [
    {
        "id": "catalogiq_overview",
        "patterns": [
            "how does catalogiq work",
            "what is catalogiq",
            "how catalogiq works",
            "catalogiq overview",
            "about catalogiq",
        ],
        "message": (
            "CatalogIQ is an AI-powered product intelligence platform designed to ingest raw, "
            "unstructured technical catalog PDFs, extract structured technical attributes with evidence "
            "traceability, validate data completeness and quality, reconcile multi-source data conflicts, "
            "generate AI commerce descriptions, and provide high-precision hybrid search and faceted filtering."
        ),
        "suggestions": [
            "How do I upload a catalog?",
            "How does search work?",
            "What is quality score?",
        ],
    },
    {
        "id": "upload_catalog",
        "patterns": [
            "how do i upload a catalog",
            "how to upload catalog",
            "how to upload a catalog",
            "uploading documents",
            "how do i upload a document",
            "upload catalog",
        ],
        "message": (
            "You can upload technical PDFs or product catalog documents up to 50MB via the Upload Page (`/upload`). "
            "Upon upload, CatalogIQ creates a document record and queues a sequential processing job that parses "
            "layouts, extracts product metadata and technical attributes, validates quality, enriches commerce "
            "descriptions, and indexes vectors into Qdrant and PostgreSQL."
        ),
        "suggestions": [
            "What happens during document processing?",
            "Why is my product marked needs review?",
            "How does search work?",
        ],
    },
    {
        "id": "search_overview",
        "patterns": [
            "how does search work",
            "how search works",
            "catalogiq search",
            "how does search work in catalogiq",
        ],
        "message": (
            "CatalogIQ search provides three operational search modes: Hybrid (default), Semantic, and Keyword. "
            "Hybrid search combines PostgreSQL lexical keyword matching with Qdrant vector semantic search "
            "using intent-weighted score fusion and exact SKU/model match priority boosting."
        ),
        "suggestions": [
            "What search modes are available?",
            "How does hybrid search work?",
            "How do filters/facets work?",
        ],
    },
    {
        "id": "quality_score",
        "patterns": [
            "what is quality score",
            "what does quality score mean",
            "how is quality score calculated",
            "quality score",
            "quality score formula",
        ],
        "message": (
            "Product Quality Score (0.0% to 100.0%) measures overall catalog health based on four weighted components:\n"
            "- **Completeness Rate** (40% weight): Percentage of expected category attributes populated.\n"
            "- **Verification Rate** (30% weight): Percentage of attributes with verified document evidence.\n"
            "- **Confidence Coverage** (20% weight): Average confidence score across extracted attributes.\n"
            "- **Review Hygiene** (10% weight): Absence of unresolved conflicts or validation errors."
        ),
        "suggestions": [
            "What does needs_review mean?",
            "Why is my product marked Needs Review?",
            "How do I fix a conflict?",
        ],
    },
    {
        "id": "needs_review",
        "patterns": [
            "what does needs review mean",
            "what does needs_review mean",
            "why is my product marked needs review",
            "why does a product need review",
            "needs review status",
        ],
        "message": (
            "A product status is set to `needs_review` when it contains low-confidence extracted attributes (<70%), "
            "missing required fields for its product category, or unresolved multi-source reconciliation conflicts. "
            "You can inspect and resolve these issues on the Human Review page (`/reviews`)."
        ),
        "suggestions": [
            "How do I fix a conflict?",
            "What is quality score?",
            "What are product statuses?",
        ],
    },
    {
        "id": "search_modes",
        "patterns": [
            "what search modes are available",
            "what search modes exist",
            "search modes",
            "available search modes",
        ],
        "message": (
            "CatalogIQ supports three search modes:\n"
            "- **Hybrid** (Default): Combines keyword and vector search with query intent detection and exact SKU priority.\n"
            "- **Semantic**: Vector search powered by Qdrant and FastEmbed (`BAAI/bge-small-en-v1.5`) capturing conceptual natural language intent.\n"
            "- **Keyword**: PostgreSQL lexical search matching SKU, Model, Name, Brand, Category, and technical attributes."
        ),
        "suggestions": [
            "How does hybrid search work?",
            "How do filters/facets work?",
            "What does search degraded mode mean?",
        ],
    },
    {
        "id": "hybrid_search",
        "patterns": [
            "how does hybrid search work",
            "how hybrid search works",
            "hybrid search",
        ],
        "message": (
            "Hybrid search merges PostgreSQL lexical candidates with Qdrant vector candidates. It detects query intent to adjust fusion weights:\n"
            "- `IDENTIFIER` queries (e.g. SKU/Model): 80% Keyword / 20% Vector\n"
            "- `NATURAL_LANGUAGE` queries: 30% Keyword / 70% Vector\n"
            "- `MIXED` queries: 50% Keyword / 50% Vector\n"
            "Exact SKU and Model matches receive clamped score boosts to guarantee exact matches outrank non-exact candidates."
        ),
        "suggestions": [
            "What search modes are available?",
            "How do filters/facets work?",
            "How does ranking work?",
        ],
    },
    {
        "id": "filters_and_facets",
        "patterns": [
            "how do filters work",
            "how do facets work",
            "how do filters and facets work",
            "how do filters/facets work",
            "filters and facets",
        ],
        "message": (
            "CatalogIQ provides multi-select filtering by category, brand, status, subcategory, and product quality score range. "
            "Faceting uses disjunctive counting (calculates counts for unselected options without restricting counts to current selection) "
            "and dynamically generates facet counts for technical product attributes."
        ),
        "suggestions": [
            "How does search work?",
            "How does ranking work?",
            "What search modes are available?",
        ],
    },
]


def normalize_faq_question(question: str) -> str:
    """
    Normalizes a user question conservatively for deterministic FAQ pattern matching:
    1. Trim leading/trailing whitespace
    2. Convert to lowercase
    3. Collapse repeated whitespace
    4. Remove leading/trailing simple punctuation (?, ., !, ,)
    """
    if not question:
        return ""
    text = question.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[?,.!\s]+|[?,.!\s]+$", "", text)
    return text.strip()


def match_faq_question(message: str) -> Optional[Dict[str, Any]]:
    """
    Checks if a normalized message matches a known high-confidence FAQ entry.
    Returns response dict if matched, or None if unknown.
    """
    normalized = normalize_faq_question(message)
    if not normalized:
        return None

    for entry in FAQ_ENTRIES:
        if normalized in entry["patterns"]:
            return {
                "message": entry["message"],
                "suggestions": entry["suggestions"],
                "is_faq": True,
            }

    return None
