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
from typing import Any, Dict, List, Optional

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

    def _generate_with_retry(self, prompt: str, config: Any, max_retries: int = 5) -> str:
        """
        Executes Gemini generate_content with automatic exponential backoff for transient errors (429, 503, quotas).
        """
        import re
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(
                    keyword in error_str
                    for keyword in ["rate", "quota", "429", "500", "503", "unavailable", "temporarily", "timeout", "resource_exhausted", "retry in"]
                )
                if attempt == max_retries or not is_transient:
                    raise
                retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str)
                if retry_match:
                    wait = float(retry_match.group(1)) + 1.5
                else:
                    wait = min(30.0, float(_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))))
                logger.warning(
                    f"Gemini transient rate/quota error (attempt {attempt}/{max_retries}), "
                    f"waiting {wait:.1f}s before retry: {e}"
                )
                time.sleep(wait)

    def _call_gemini(self, user_prompt: str) -> str:
        """
        Calls Gemini with system + user messages and returns the raw text response.
        Retries on transient errors (rate limits, 5xx).
        """
        full_prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"
        config = self._types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=4096,
        )

        try:
            return self._generate_with_retry(full_prompt, config)
        except Exception as e:
            raise ExtractionError(f"Gemini extraction failed: {e}") from e

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

        import re
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = re.sub(r"^```(?:json)?\s*", "", cleaned_content)
            cleaned_content = re.sub(r"\s*```$", "", cleaned_content).strip()

        try:
            raw_data = json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            raise ExtractionError(
                f"Gemini returned non-JSON response. Raw: {raw_content[:500]}"
            ) from e

        # Normalize raw_data into a dictionary for ExtractionResult
        if isinstance(raw_data, list):
            if len(raw_data) > 0 and isinstance(raw_data[0], dict):
                first_item = raw_data[0]
                if "raw_value" in first_item or "specification" in first_item or "attribute" in first_item:
                    raw_dict = {"attributes": raw_data}
                else:
                    raw_dict = dict(first_item)
                    all_attrs = []
                    for item in raw_data:
                        if isinstance(item, dict) and "attributes" in item and isinstance(item["attributes"], list):
                            all_attrs.extend(item["attributes"])
                    if all_attrs:
                        raw_dict["attributes"] = all_attrs
            else:
                raw_dict = {}
        elif isinstance(raw_data, dict):
            raw_dict = dict(raw_data)
            for wrapper in ["products", "items", "catalog", "records", "data"]:
                if wrapper in raw_dict and isinstance(raw_dict[wrapper], list) and len(raw_dict[wrapper]) > 0:
                    first = raw_dict[wrapper][0]
                    if isinstance(first, dict):
                        for k, v in first.items():
                            if k not in raw_dict or not raw_dict[k]:
                                raw_dict[k] = v
                    break
        else:
            raw_dict = {}

        # Handle aliases from industrial datasets
        if "Mfg_Part_Num" in raw_dict and ("sku" not in raw_dict or not raw_dict["sku"]):
            raw_dict["sku"] = str(raw_dict["Mfg_Part_Num"])
        if "Part_Desc" in raw_dict:
            if "product_name" not in raw_dict or not raw_dict["product_name"]:
                raw_dict["product_name"] = str(raw_dict["Part_Desc"])
            if "description" not in raw_dict or not raw_dict["description"]:
                raw_dict["description"] = str(raw_dict["Part_Desc"])
        if "Unilog_Brand" in raw_dict or "E1_Brand" in raw_dict or "Part_Manuf" in raw_dict:
            if "brand" not in raw_dict or not raw_dict["brand"]:
                brand_val = raw_dict.get("Unilog_Brand") or raw_dict.get("E1_Brand") or raw_dict.get("Part_Manuf")
                if brand_val:
                    raw_dict["brand"] = str(brand_val)

        try:
            result = ExtractionResult(**raw_dict)
        except Exception as e:
            raw_keys = list(raw_dict.keys()) if isinstance(raw_dict, dict) else str(type(raw_dict))
            raise ExtractionError(
                f"Gemini response failed Pydantic validation: {e}. Raw dict keys: {raw_keys}"
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
        
        config = self._types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=4096,
        )

        try:
            raw_content = self._generate_with_retry(full_prompt, config)
        except Exception as e:
            raise EnrichmentError(f"Gemini enrichment call failed: {e}") from e

        import re
        cleaned_content = raw_content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = re.sub(r"^```(?:json)?\s*", "", cleaned_content)
            cleaned_content = re.sub(r"\s*```$", "", cleaned_content).strip()

        try:
            raw_data = json.loads(cleaned_content)
            if isinstance(raw_data, list) and len(raw_data) > 0 and isinstance(raw_data[0], dict):
                raw_data = raw_data[0]
            elif not isinstance(raw_data, dict):
                raw_data = {}
            enrichment = CommerceEnrichment(**raw_data)
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

        logger.info(f"Sending low-latency assistant request to Gemini model: {self._model}")

        try:
            assistant_config = self._types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=1536,
            )
            raw_content = self._generate_with_retry(full_prompt, assistant_config)
        except Exception as e:
            logger.error(f"Gemini assistant call failure: {e}")
            raise RuntimeError(f"Gemini assistant call failed: {e}") from e

        try:
            cleaned_json = raw_content.strip()
            if cleaned_json.startswith("```"):
                cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
                cleaned_json = re.sub(r"\s*```$", "", cleaned_json)
            
            raw_dict = {}
            try:
                raw_dict = json.loads(cleaned_json, strict=False)
            except Exception:
                # Robust extraction if json was truncated or had unescaped characters
                match_msg = re.search(r'"message"\s*:\s*"(.*?)(?:"\s*,\s*"suggestions"|"\s*\Z)', cleaned_json, re.DOTALL)
                if match_msg:
                    extracted = match_msg.group(1).rstrip('"} \n\r')
                    extracted = extracted.replace('\\"', '"').replace('\\n', '\n')
                    raw_dict = {"message": extracted}
                else:
                    raw_dict = {"message": cleaned_json}

            res_msg = str(
                raw_dict.get("message")
                or raw_dict.get("reply")
                or raw_dict.get("response")
                or raw_dict.get("answer")
                or raw_dict.get("text")
                or ""
            ).strip()
            if not res_msg:
                res_msg = raw_content
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
                "message": raw_content.strip(),
                "suggestions": [
                    "How do I upload a catalog?",
                    "How does search work?",
                    "What does quality score mean?",
                ],
            }


