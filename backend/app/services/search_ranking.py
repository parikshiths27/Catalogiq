"""
Search Ranking and Intent Classification Service for CatalogIQ.
Provides deterministic query intent classification, intent-weighted score fusion,
explicit exact-match priority ranking, and deterministic tie-breaking.
"""
import re
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    IDENTIFIER = "IDENTIFIER"
    NATURAL_LANGUAGE = "NATURAL_LANGUAGE"
    MIXED = "MIXED"


class ExactMatchPriority(int, Enum):
    EXACT_SKU = 3
    EXACT_MODEL = 2
    EXACT_NAME = 1
    NONE = 0


class IntentWeights(BaseModel):
    keyword_weight: float
    semantic_weight: float


INTENT_WEIGHTS_MAP: Dict[QueryIntent, IntentWeights] = {
    QueryIntent.IDENTIFIER: IntentWeights(keyword_weight=0.80, semantic_weight=0.20),
    QueryIntent.NATURAL_LANGUAGE: IntentWeights(keyword_weight=0.30, semantic_weight=0.70),
    QueryIntent.MIXED: IntentWeights(keyword_weight=0.50, semantic_weight=0.50),
}


class SearchRankingService:
    """
    Service responsible for query intent detection, candidate pool sizing,
    exact-match priority computation, intent-weighted score fusion, and tie-breaking.
    """

    @staticmethod
    def classify_query_intent(query: str) -> QueryIntent:
        """
        Classifies query into IDENTIFIER, NATURAL_LANGUAGE, or MIXED using deterministic pattern matching.
        """
        if not query or not query.strip():
            return QueryIntent.NATURAL_LANGUAGE

        raw_query = query.strip()
        tokens = [t for t in re.split(r"\s+", raw_query) if t]

        if not tokens:
            return QueryIntent.NATURAL_LANGUAGE

        # Identifier regex pattern: contains hyphen, slash, digits with letters, or model patterns like MX500-230, M3BP, ABC-123
        identifier_token_pattern = re.compile(
            r"^([a-zA-Z0-9]+[\-_/][a-zA-Z0-9\-_/]+|[a-zA-Z]+[0-9]+[a-zA-Z0-9]*|[0-9]+[a-zA-Z]+[a-zA-Z0-9]*)$",
            re.IGNORECASE,
        )

        id_token_count = sum(1 for t in tokens if identifier_token_pattern.match(t))
        total_tokens = len(tokens)

        # Single short token matching identifier pattern or single code token
        if total_tokens == 1:
            if id_token_count == 1 or re.search(r"\d", tokens[0]):
                return QueryIntent.IDENTIFIER
            return QueryIntent.NATURAL_LANGUAGE

        # Multi-token queries
        if id_token_count == total_tokens:
            return QueryIntent.IDENTIFIER
        elif id_token_count > 0:
            return QueryIntent.MIXED
        else:
            # Check for numeric technical specs (e.g. "11 kW", "400V", "50Hz")
            spec_pattern = re.compile(r"\b\d+(\.\d+)?\s*(kw|v|hz|rpm|hp|mm|a|bar|°c)\b", re.IGNORECASE)
            if spec_pattern.search(raw_query):
                return QueryIntent.MIXED
            return QueryIntent.NATURAL_LANGUAGE

    @staticmethod
    def get_candidate_pool_size(limit: int) -> int:
        """Returns candidate pool limit: max(50, limit * 5)."""
        return max(50, limit * 5)

    @staticmethod
    def compute_exact_priority(
        query_norm: str,
        sku: Optional[str],
        model: Optional[str],
        product_name: Optional[str],
    ) -> ExactMatchPriority:
        """
        Determines deterministic exact-match priority:
        EXACT_SKU (3) > EXACT_MODEL (2) > EXACT_NAME (1) > NONE (0)
        """
        p_sku = (sku or "").strip().lower()
        p_model = (model or "").strip().lower()
        p_name = (product_name or "").strip().lower()

        if p_sku and p_sku == query_norm:
            return ExactMatchPriority.EXACT_SKU
        if p_model and p_model == query_norm:
            return ExactMatchPriority.EXACT_MODEL
        if p_name and p_name == query_norm:
            return ExactMatchPriority.EXACT_NAME
        return ExactMatchPriority.NONE

    @staticmethod
    def fuse_scores(
        keyword_score: float,
        similarity_score: float,
        intent: QueryIntent,
        exact_priority: ExactMatchPriority,
    ) -> float:
        """
        Computes intent-weighted fused hybrid score with exact-match boost clamping.
        """
        weights = INTENT_WEIGHTS_MAP[intent]
        base_fused = (weights.keyword_weight * keyword_score) + (weights.semantic_weight * similarity_score)

        exact_boost = 0.0
        if exact_priority == ExactMatchPriority.EXACT_SKU:
            exact_boost = 0.30
        elif exact_priority == ExactMatchPriority.EXACT_MODEL:
            exact_boost = 0.25
        elif exact_priority == ExactMatchPriority.EXACT_NAME:
            exact_boost = 0.15

        return round(min(1.0000, base_fused + exact_boost), 4)

    @staticmethod
    def compute_attribute_relevance(
        query_lower: str,
        attributes: List[Any],
    ) -> float:
        """
        Calculates Task 8.5 attribute match relevance signal:
        - 0.75 for exact raw_value or display_name match
        - 0.55 for partial text match
        - 0.00 for no match
        """
        if not query_lower or not attributes:
            return 0.0

        max_attr_score = 0.0
        for attr in attributes:
            r_val = (getattr(attr, "raw_value", "") or "").strip().lower()
            d_val = (getattr(attr, "display_name", "") or "").strip().lower()

            if r_val == query_lower or d_val == query_lower:
                max_attr_score = max(max_attr_score, 0.75)
            elif query_lower in r_val or query_lower in d_val:
                max_attr_score = max(max_attr_score, 0.55)

        return max_attr_score
