"""
GeminiProvider — LLM provider for production using Google Gemini.

Uses the google-genai SDK (from google import genai).
Targets gemini-3.6-flash (configurable via GEMINI_MODEL).

All Gemini-specific SDK code is ISOLATED to this file.
The rest of the application depends only on BaseLLMProvider.

Retry logic:
  - Up to 3 attempts on transient API errors (rate limits, server errors).
  - Raises ConfigurationError on missing API key or invalid model.
  - Raises ExtractionError if all retries are exhausted.
"""
import json
import logging
import time
from typing import Any, Dict

from app.core.config import settings
from app.services.llm.base import (
    BaseLLMProvider,
    CommerceEnrichment,
    ConfigurationError,
    ExtractionError,
    ExtractionResult,
)
from app.services.llm.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    build_extraction_prompt,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 3


class GeminiProvider(BaseLLMProvider):
    """
    LLM provider using Google Gemini (gemini-3.6-flash by default).

    Configuration via environment:
        GEMINI_API_KEY  — required (raises ConfigurationError if missing)
        GEMINI_MODEL    — defaults to gemini-3.6-flash
    """

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ConfigurationError(
                "GEMINI_API_KEY environment variable is not set. "
                "Set it in .env or environment to use the Gemini provider."
            )

        # Import and configure the google-genai SDK
        # All SDK imports are isolated here — no google-genai imports elsewhere
        try:
            from google import genai  # type: ignore[import]
            from google.genai import types  # type: ignore[import]
            self._genai = genai
            self._types = types
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        except ImportError as e:
            raise ConfigurationError(
                "google-genai package is not installed. "
                "Run: pip install google-genai"
            ) from e

        self._model = settings.GEMINI_MODEL
        self._prompt_version = PROMPT_VERSION
        logger.info(f"GeminiProvider initialized: model={self._model}")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def _call_gemini(self, user_prompt: str) -> str:
        """
        Calls Gemini with system + user messages and returns the raw text response.
        Retries on transient errors (rate limits, 5xx).
        """
        full_prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=full_prompt,
                    config=self._types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                        max_output_tokens=4096,
                    ),
                )
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(
                    keyword in error_str
                    for keyword in ["rate", "quota", "429", "500", "503", "timeout"]
                )
                if attempt == _MAX_RETRIES:
                    raise ExtractionError(
                        f"Gemini extraction failed after {_MAX_RETRIES} attempts: {e}"
                    ) from e
                if is_transient:
                    wait = _RETRY_DELAY_SECONDS * attempt
                    logger.warning(
                        f"Gemini transient error (attempt {attempt}/{_MAX_RETRIES}), "
                        f"retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    raise ExtractionError(f"Gemini extraction non-retryable error: {e}") from e

        raise ExtractionError("Gemini extraction failed: exhausted all retries")

    def extract(self, ir: Dict[str, Any]) -> ExtractionResult:
        """
        Sends the document IR to Gemini and returns a validated ExtractionResult.

        Process:
          1. Build the prompt from the IR.
          2. Call Gemini with JSON response mime type enforced.
          3. Parse the text response as JSON.
          4. Validate through ExtractionResult Pydantic model.
          5. Stamp provider metadata onto the result.

        Raises:
            ExtractionError: If the response fails validation or is malformed.
            ConfigurationError: If API key or model is misconfigured.
        """
        user_prompt = build_extraction_prompt(ir)
        logger.info(f"Sending extraction request to Gemini model: {self._model}")
        raw_content = self._call_gemini(user_prompt)

        try:
            raw_dict = json.loads(raw_content)
        except json.JSONDecodeError as e:
            raise ExtractionError(
                f"Gemini returned non-JSON response. Raw: {raw_content[:500]}"
            ) from e

        try:
            result = ExtractionResult(**raw_dict)
        except Exception as e:
            raise ExtractionError(
                f"Gemini response failed Pydantic validation: {e}. Raw dict keys: {list(raw_dict.keys())}"
            ) from e

        # Stamp provider metadata
        result.provider_name = self.provider_name
        result.model_name = self.model_name
        result.prompt_version = self.prompt_version

        logger.info(
            f"Gemini extraction successful: {len(result.attributes)} attributes extracted"
        )
        return result

    def enrich(self, product_context: Dict[str, Any]) -> CommerceEnrichment:
        """
        Generates structured AI commerce content using Google Gemini.
        """
        from app.services.llm.base import CommerceEnrichment, EnrichmentError
        from app.services.llm.prompts import (
            ENRICHMENT_PROMPT_VERSION,
            ENRICHMENT_SYSTEM_PROMPT,
            build_enrichment_prompt,
        )

        user_prompt = build_enrichment_prompt(product_context)
        full_prompt = f"{ENRICHMENT_SYSTEM_PROMPT}\n\n{user_prompt}"

        logger.info(f"Sending enrichment request to Gemini model: {self._model}")
        
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                    max_output_tokens=4096,
                ),
            )
            raw_content = response.text
        except Exception as e:
            raise EnrichmentError(f"Gemini enrichment call failed: {e}") from e

        try:
            raw_dict = json.loads(raw_content)
            enrichment = CommerceEnrichment(**raw_dict)
            enrichment.provider_name = self.provider_name
            enrichment.model_name = self.model_name
            enrichment.prompt_version = ENRICHMENT_PROMPT_VERSION
            return enrichment
        except Exception as e:
            raise EnrichmentError(f"Gemini enrichment response failed Pydantic validation: {e}") from e

    def generate_assistant_response(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates grounded CatalogIQ Help Center response using Google Gemini.
        """
        from app.services.assistant_prompts import (
            CATALOGIQ_ASSISTANT_SYSTEM_PROMPT,
            build_assistant_user_prompt,
        )

        user_prompt = build_assistant_user_prompt(message=message, history=history, context=context)
        full_prompt = f"{CATALOGIQ_ASSISTANT_SYSTEM_PROMPT}\n\n{user_prompt}"

        logger.info(f"Sending assistant request to Gemini model: {self._model}")

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config=self._types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            )
            raw_content = response.text
        except Exception as e:
            logger.error(f"Gemini assistant call failure: {e}")
            raise RuntimeError(f"Gemini assistant call failed: {e}") from e

        try:
            raw_dict = json.loads(raw_content)
            res_msg = str(raw_dict.get("message") or "")
            res_sug = raw_dict.get("suggestions") or []
            if not isinstance(res_sug, list):
                res_sug = []
            return {
                "message": res_msg,
                "suggestions": [str(s) for s in res_sug if isinstance(s, (str, int, float))],
            }
        except Exception as e:
            logger.warning(f"Failed to parse JSON assistant output from Gemini, returning fallback text: {e}")
            return {
                "message": raw_content,
                "suggestions": [
                    "How do I upload a catalog?",
                    "How does search work?",
                    "What does quality score mean?",
                ],
            }


