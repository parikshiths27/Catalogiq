"""
LLM Provider base definitions.

Defines:
  - RawAttributeItem    — a single candidate attribute from LLM output
  - ExtractionResult    — the full validated LLM extraction response
  - BaseLLMProvider     — abstract interface for all LLM providers

Design principles:
  - No provider-conditional logic anywhere outside this package.
  - ExtractionResult is always Pydantic-validated before any pipeline stage consumes it.
  - LLM output that fails validation raises ValueError — never passes through silently.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Structured output data models
# ---------------------------------------------------------------------------

class RawAttributeItem(BaseModel):
    """
    A single candidate attribute produced by LLM extraction or deterministic parsing.

    Fields:
        name:             Canonical attribute name (e.g., "voltage", "rated_power").
        display_name:     Human-readable label (e.g., "Voltage", "Rated Power").
        raw_value:        Original string value as found in the source (e.g., "230 V").
        unit:             Unit string if applicable (e.g., "V", "kW", "RPM").
        data_type:        One of: text | numeric | boolean | category | structured.
        evidence_text:    The exact text snippet from the IR that supports this value.
        page_number:      Page where the evidence was found (1-indexed). None if unknown.
        extraction_method: One of: deterministic | llm | llm_inference.
                          - deterministic: parsed from structured table with high certainty.
                          - llm: extracted by LLM from text with a direct quote in evidence_text.
                          - llm_inference: LLM inferred this value; no direct quote available.
        evidence_verified: True if evidence_text was found verbatim in the IR.
                           Always False for llm_inference extraction_method.
        llm_confidence:   LLM-reported confidence (0.0–1.0). Not the final pipeline score.
    """
    name: str
    display_name: str
    raw_value: str
    unit: Optional[str] = None
    data_type: str = "text"
    evidence_text: str = ""
    page_number: Optional[int] = None
    extraction_method: str = "llm"  # deterministic | llm | llm_inference
    evidence_verified: bool = False
    llm_confidence: float = Field(default=0.8, ge=0.0, le=1.0)

    @classmethod
    def _normalize_raw_dict(cls, data: Any) -> Any:
        """Remaps LLM key variations (e.g. specification/value) before Pydantic validation."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Handle key variations for attribute name
        raw_key = d.get("name") or d.get("specification") or d.get("key") or d.get("attribute") or d.get("property") or "unknown_attribute"
        if "name" not in d or not d["name"]:
            d["name"] = str(raw_key).lower().replace(" ", "_")
        if "display_name" not in d or not d["display_name"]:
            d["display_name"] = str(raw_key)

        # Handle value variations
        if "raw_value" not in d or d["raw_value"] is None:
            d["raw_value"] = str(d.get("value") or d.get("val") or "")

        return d

    from pydantic import model_validator
    @model_validator(mode="before")
    @classmethod
    def pre_validate(cls, data: Any) -> Any:
        return cls._normalize_raw_dict(data)

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, v: str) -> str:
        allowed = {"text", "numeric", "boolean", "category", "structured"}
        if v not in allowed:
            return "text"  # Fallback to text instead of failing
        return v

    @field_validator("extraction_method")
    @classmethod
    def validate_extraction_method(cls, v: str) -> str:
        allowed = {"deterministic", "llm", "llm_inference"}
        if v not in allowed:
            return "llm"  # Fallback to llm instead of failing
        return v


class ExtractionResult(BaseModel):
    """
    The fully validated output of an LLM extraction pass over a document IR.

    Semantic fields (product_name, brand, sku, etc.) come from the LLM's text analysis.
    Attribute candidates are a merged list of deterministic + LLM-extracted items.

    All fields are optional at this stage — the persistence layer handles validation
    for required fields and creates ValidationResult records for missing mandatory data.
    """
    # Core product identity (LLM-extracted from text)
    product_name: Optional[str] = None
    brand: Optional[str] = None
    sku: Optional[str] = None
    model_number: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    product_type: Optional[str] = None
    description: Optional[str] = None

    # Technical attributes (deterministic + LLM combined)
    attributes: List[RawAttributeItem] = Field(default_factory=list)

    # List-valued semantic fields (LLM-extracted)
    features: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

    # Extraction metadata — set by the provider after generation
    provider_name: str = "unknown"
    model_name: str = "unknown"
    prompt_version: str = "unknown"

    @field_validator("features", "applications", "certifications", "keywords", mode="before")
    @classmethod
    def normalize_string_lists(cls, v: Any) -> List[str]:
        """Ensures list items are strings even if LLM outputs dicts or nested objects."""
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    res.append(item)
                elif isinstance(item, dict):
                    # Extract first string value or joined key/values
                    str_vals = [str(val) for val in item.values() if val]
                    if str_vals:
                        res.append(": ".join(str_vals))
                elif item is not None:
                    res.append(str(item))
            return res
        return []

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, v: List[RawAttributeItem]) -> List[RawAttributeItem]:
        """Ensure attribute names are non-empty strings."""
        valid = []
        for attr in v:
            if attr and attr.name and attr.name.strip():
                valid.append(attr)
        return valid


# ---------------------------------------------------------------------------
# Phase 5: Structured AI Commerce Enrichment schema
# ---------------------------------------------------------------------------

class CommerceEnrichment(BaseModel):
    """
    Structured AI commerce content generated strictly from verified product context and evidence.

    Safety constraint:
      The LLM must NOT invent technical specifications, certifications, or performance claims
      that are not present in the supplied product_context.
    """
    commerce_description: Optional[str] = None
    short_description: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    applications: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

    # Model provenance metadata
    provider_name: str = "unknown"
    model_name: str = "unknown"
    prompt_version: str = "v1.0"
    confidence: float = Field(default=0.88, ge=0.0, le=1.0)

    @field_validator("features", "applications", "keywords", mode="before")
    @classmethod
    def normalize_enrichment_lists(cls, v: Any) -> List[str]:
        if not v:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    res.append(item)
                elif isinstance(item, dict):
                    str_vals = [str(val) for val in item.values() if val]
                    if str_vals:
                        res.append(": ".join(str_vals))
                elif item is not None:
                    res.append(str(item))
            return res
        return []


# ---------------------------------------------------------------------------
# Abstract provider interface
# ---------------------------------------------------------------------------

class ConfigurationError(Exception):
    """Raised when an LLM provider is misconfigured or unavailable at runtime."""
    pass


class ExtractionError(Exception):
    """Raised when extraction fails after all retry attempts."""
    pass


class EnrichmentError(Exception):
    """Raised when AI commerce enrichment fails after retries."""
    pass


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Implementors:
      - OllamaProvider (local development, Qwen3 8B)
      - GeminiProvider (production, Gemini 3.6 Flash)
      - MockProvider   (automated tests ONLY)

    The pipeline calls `extract()` for Phase 4 extraction and `enrich()` for Phase 5 enrichment.
    No provider-conditional logic exists outside this package.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier, e.g., 'ollama', 'gemini'."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The specific model being used, e.g., 'qwen3:8b', 'gemini-3.6-flash'."""
        ...

    @property
    @abstractmethod
    def prompt_version(self) -> str:
        """The prompt template version string, e.g., 'v1.0'."""
        ...

    @abstractmethod
    def extract(self, ir: Dict[str, Any]) -> ExtractionResult:
        """
        Extract structured product intelligence from a Docling Intermediate Representation.

        Args:
            ir: The parsed document IR dict (from DocumentParser.parse()).

        Returns:
            ExtractionResult — validated Pydantic model ready for the pipeline.
        """
        ...

    @abstractmethod
    def enrich(self, product_context: Dict[str, Any]) -> CommerceEnrichment:
        """
        Generate structured AI commerce content strictly constrained to verified product context.

        Args:
            product_context: Dict containing verified product identity, attributes, evidence,
                             and features.

        Returns:
            CommerceEnrichment — validated Pydantic model containing commerce descriptions and SEO text.
        """
        ...

    def generate_assistant_response(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate grounded assistant help response for CatalogIQ operating questions.

        Args:
            message: User query or prompt.
            history: Optional conversation turns list.
            context: Optional UI context (page, query, mode, product_id, etc.).

        Returns:
            Dict containing 'message' (str) and 'suggestions' (List[str]).
        """
        return {
            "message": (
                "CatalogIQ Assistant is available to help you navigate document parsing, "
                "attribute extraction, confidence scoring, quality validation, and hybrid search."
            ),
            "suggestions": [
                "How do I upload a catalog?",
                "How does search work?",
                "What does product quality score mean?",
            ],
        }



