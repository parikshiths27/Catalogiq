"""
CatalogIQ Assistant Service.
Provides in-product grounded help, workflow guidance, and troubleshooting support
by interfacing with the configured LLM provider (GeminiProvider in production).
"""
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.services.llm.base import BaseLLMProvider, ConfigurationError
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)


class ChatMessageTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantChatRequest(BaseModel):
    message: str = Field(..., description="User question or prompt")
    history: Optional[List[ChatMessageTurn]] = Field(default=None, description="Recent conversation turns")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Lightweight UI context (page, query, mode, product_id)")


class AssistantChatResponse(BaseModel):
    message: str
    suggestions: List[str] = Field(default_factory=list)


class AssistantService:
    """
    Service responsible for constructing grounded CatalogIQ system context,
    invoking the existing LLM provider, and returning structured help responses.
    """

    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self._provider = provider

    @property
    def provider(self) -> BaseLLMProvider:
        if self._provider is None:
            self._provider = get_llm_provider()
        return self._provider

    def answer_question(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssistantChatResponse:
        """
        Processes a user question, constructs CatalogIQ system context, and returns a grounded response.
        """
        if not message or not message.strip():
            raise ValueError("Message cannot be empty.")

        raw_msg = message.strip()

        try:
            res_dict = self.provider.generate_assistant_response(
                message=raw_msg,
                history=history,
                context=context,
            )
            return AssistantChatResponse(
                message=res_dict.get("message", "CatalogIQ Assistant is available to help."),
                suggestions=res_dict.get("suggestions", []),
            )
        except ConfigurationError as e:
            logger.error(f"LLM Provider configuration error in AssistantService: {e}")
            return AssistantChatResponse(
                message=(
                    "CatalogIQ Assistant is temporarily unavailable because the AI provider is not configured. "
                    "You can continue using CatalogIQ normally."
                ),
                suggestions=[
                    "How do I upload a catalog?",
                    "How does search work?",
                    "What does product status mean?",
                ],
            )
        except Exception as e:
            logger.error(f"Assistant error processing question: {e}")
            return AssistantChatResponse(
                message=(
                    "CatalogIQ Assistant encountered a temporary communication issue. "
                    "You can continue using CatalogIQ normally."
                ),
                suggestions=[
                    "How do I upload a catalog?",
                    "How does search work?",
                    "What is quality score?",
                ],
            )
