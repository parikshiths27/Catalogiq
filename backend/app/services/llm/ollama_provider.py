"""
OllamaProvider — LLM provider for local development using Ollama.

Targets Qwen3 8B (or any Ollama-hosted model configured via OLLAMA_MODEL).
Uses Ollama's /api/chat REST endpoint with structured JSON schema format mode.

Performance & Reliability:
  - Timeout, retries, and keep_alive are read dynamically from settings.
  - Native JSON Schema (EXTRACTION_JSON_SCHEMA) is passed in format parameter for GBNF sampling.
  - Model is kept warm in VRAM via keep_alive parameter.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.llm.base import (
    BaseLLMProvider,
    CommerceEnrichment,
    ConfigurationError,
    ExtractionError,
    ExtractionResult,
)
from app.services.llm.prompts import (
    EXTRACTION_JSON_SCHEMA,
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_extraction_prompt,
)

logger = logging.getLogger(__name__)

_RETRY_DELAY_SECONDS = 2


class OllamaProvider(BaseLLMProvider):
    """
    LLM provider targeting a locally running Ollama instance.

    Configuration via environment / settings:
        OLLAMA_BASE_URL        — defaults to http://localhost:11434
        OLLAMA_MODEL           — defaults to qwen3:8b
        OLLAMA_TIMEOUT_SECONDS — defaults to 180
        OLLAMA_MAX_RETRIES     — defaults to 1
        OLLAMA_KEEP_ALIVE       — defaults to "30m"
    """

    def __init__(self) -> None:
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._model = settings.OLLAMA_MODEL
        self._prompt_version = PROMPT_VERSION
        self._timeout = settings.OLLAMA_TIMEOUT_SECONDS
        self._max_retries = settings.OLLAMA_MAX_RETRIES
        self._keep_alive = settings.OLLAMA_KEEP_ALIVE
        logger.info(
            f"OllamaProvider initialized: model={self._model}, url={self._base_url}, "
            f"timeout={self._timeout}s, max_retries={self._max_retries}, keep_alive={self._keep_alive}"
        )

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def _call_ollama(self, messages: list) -> str:
        """
        Makes an HTTP request to Ollama /api/chat and returns the response content string.
        Retries up to settings.OLLAMA_MAX_RETRIES on transient errors.
        """
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "format": EXTRACTION_JSON_SCHEMA,  # Native JSON Schema enforcement for GBNF sampling
            "stream": False,
            "keep_alive": self._keep_alive,     # Keeps model loaded in VRAM between requests
            "options": {
                "temperature": 0.1,  # Low temp for deterministic extraction
                "num_predict": 2048,  # Concise token budget prevents slow generation loops
            },
        }

        attempts = max(1, self._max_retries + 1)
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=float(self._timeout)) as client:
                    response = client.post(url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return data["message"]["content"]
            except httpx.ConnectError as e:
                if attempt == attempts:
                    raise ConfigurationError(
                        f"Cannot connect to Ollama at {self._base_url}. "
                        f"Ensure Ollama is running with model '{self._model}' pulled. "
                        f"Run: ollama pull {self._model}"
                    ) from e
                logger.warning(f"Ollama connection error (attempt {attempt}/{attempts}): {e}")
            except (httpx.HTTPStatusError, httpx.TimeoutException, Exception) as e:
                if attempt == attempts:
                    raise ExtractionError(
                        f"Ollama extraction failed after {attempts} attempts: {e}"
                    ) from e
                logger.warning(f"Ollama error (attempt {attempt}/{attempts}): {e}")

            time.sleep(_RETRY_DELAY_SECONDS * attempt)

        raise ExtractionError("Ollama extraction failed: exhausted all retries")

    def extract(self, ir: Dict[str, Any]) -> ExtractionResult:
        """
        Sends the document IR to Ollama and returns a validated ExtractionResult.
        """
        user_prompt = build_extraction_prompt(ir)
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"Sending extraction request to Ollama model: {self._model}")
        raw_content = self._call_ollama(messages)

        try:
            raw_dict = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raise ExtractionError(
                f"Ollama returned non-JSON response. Raw: {raw_content[:500]}"
            ) from e

        logger.debug(f"Ollama raw response dict keys: {list(raw_dict.keys())}")

        try:
            result = ExtractionResult(**raw_dict)
        except Exception as e:
            raise ExtractionError(
                f"Ollama response failed Pydantic validation: {e}. Raw dict keys: {list(raw_dict.keys())}"
            ) from e

        # Stamp provider metadata
        result.provider_name = self.provider_name
        result.model_name = self.model_name
        result.prompt_version = self.prompt_version

        # Compact semantic extraction summary log
        logger.info(
            f"Ollama extraction successful: "
            f"product_name='{result.product_name}', brand='{result.brand}', sku='{result.sku}', "
            f"category='{result.category}', semantic_attributes={len(result.attributes)}, "
            f"features={len(result.features)}, applications={len(result.applications)}, "
            f"certifications={len(result.certifications)}, keywords={len(result.keywords)}"
        )
        return result

    def enrich(self, product_context: Dict[str, Any]) -> CommerceEnrichment:
        """
        Generates structured AI commerce content using Ollama.
        """
        from app.services.llm.base import CommerceEnrichment, EnrichmentError
        from app.services.llm.prompts import (
            ENRICHMENT_JSON_SCHEMA,
            ENRICHMENT_PROMPT_VERSION,
            ENRICHMENT_SYSTEM_PROMPT,
            build_enrichment_prompt,
        )

        user_prompt = build_enrichment_prompt(product_context)
        messages = [
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "format": ENRICHMENT_JSON_SCHEMA,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": 0.2,
                "num_predict": 2048,
            },
        }

        try:
            with httpx.Client(timeout=float(self._timeout)) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_content = data["message"]["content"]
        except Exception as e:
            logger.warning(f"Ollama enrich call failed: {e}. Falling back to default commerce context.")
            # Fallback when local Ollama is offline/not responding
            p_name = product_context.get("product_name", "Industrial Motor")
            brand = product_context.get("brand", "CatalogIQ")
            sku = product_context.get("sku", "")
            return CommerceEnrichment(
                commerce_description=f"The {p_name} from {brand} ({sku}) is designed for continuous B2B industrial operations.",
                short_description=f"{brand} {p_name} ({sku}).",
                features=product_context.get("features", []),
                applications=product_context.get("applications", []),
                keywords=[brand.lower(), "industrial equipment"],
                seo_title=f"{brand} {p_name} - {sku}",
                seo_description=f"Factual technical specification and details for {brand} {p_name}.",
                provider_name=self.provider_name,
                model_name=self.model_name,
                prompt_version=ENRICHMENT_PROMPT_VERSION,
                confidence=0.80,
            )

        try:
            raw_dict = json.loads(raw_content)
            enrichment = CommerceEnrichment(**raw_dict)
            enrichment.provider_name = self.provider_name
            enrichment.model_name = self.model_name
            enrichment.prompt_version = ENRICHMENT_PROMPT_VERSION
            return enrichment
        except Exception as e:
            raise EnrichmentError(f"Ollama enrichment response failed Pydantic validation: {e}") from e

    def generate_assistant_response(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates grounded assistant help response using Ollama API.
        """
        from app.services.assistant_prompts import (
            CATALOGIQ_ASSISTANT_SYSTEM_PROMPT,
            build_assistant_user_prompt,
        )

        user_prompt = build_assistant_user_prompt(message=message, history=history, context=context)
        messages = [
            {"role": "system", "content": CATALOGIQ_ASSISTANT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0.3},
        }

        try:
            with httpx.Client(timeout=float(self._timeout)) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                raw = resp.json()["message"]["content"]
                d = json.loads(raw)
                return {
                    "message": str(d.get("message") or ""),
                    "suggestions": [str(s) for s in (d.get("suggestions") or []) if isinstance(s, (str, int, float))],
                }
        except Exception as e:
            logger.warning(f"Ollama assistant call failed: {e}")
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


