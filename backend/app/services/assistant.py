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
    reply: Optional[str] = None
    suggestions: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.reply:
            self.reply = self.message


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

        # Check deterministic fast-path FAQ layer first
        from app.services.assistant_faq import match_faq_question
        faq_match = match_faq_question(raw_msg)
        if faq_match:
            logger.info(f"Assistant FAQ fast-path match triggered for query: '{raw_msg}'")
            return AssistantChatResponse(
                message=faq_match["message"],
                suggestions=faq_match["suggestions"],
            )

        # Augment context with product data from database if referenced
        enriched_context = dict(context or {})
        try:
            from app.core.database import engine
            from sqlmodel import Session, select
            from app.models import Product, ProductAttribute, ValidationResult, ValidationStatus, AttributeEvidence
            import re

            with Session(engine) as session:
                target_product = None
                # Check if product_id is in context
                if enriched_context.get("product_id"):
                    try:
                        import uuid
                        p_uuid = uuid.UUID(str(enriched_context["product_id"]))
                        target_product = session.get(Product, p_uuid)
                    except Exception:
                        pass

                # If no product found yet, check if message mentions a SKU/MPN in database
                if not target_product:
                    tokens = re.findall(r"\b[A-Za-z0-9\-_]{4,}\b", raw_msg)
                    for tok in tokens:
                        p = session.exec(
                            select(Product).where(
                                (Product.sku.ilike(f"%{tok}%")) | (Product.model.ilike(f"%{tok}%"))
                            )
                        ).first()
                        if p:
                            target_product = p
                            break

                if target_product:
                    attrs = session.exec(
                        select(ProductAttribute).where(ProductAttribute.product_id == target_product.id)
                    ).all()
                    vals = session.exec(
                        select(ValidationResult).where(
                            ValidationResult.product_id == target_product.id,
                            ValidationResult.status == ValidationStatus.open,
                        )
                    ).all()
                    evidences = session.exec(
                        select(AttributeEvidence).where(
                            AttributeEvidence.attribute_id.in_([a.id for a in attrs])
                        )
                    ).all() if attrs else []

                    evidence_map = {}
                    for ev in evidences:
                        evidence_map[str(ev.attribute_id)] = {
                            "source_name": ev.source_name,
                            "page_number": ev.page_number,
                            "evidence_text": ev.evidence_text,
                            "extraction_method": ev.extraction_method,
                        }

                    enriched_context["product_facts"] = {
                        "product_id": str(target_product.id),
                        "sku": target_product.sku,
                        "brand": target_product.brand,
                        "model": target_product.model,
                        "product_name": target_product.product_name,
                        "category": target_product.category,
                        "status": str(target_product.status.value if hasattr(target_product.status, "value") else target_product.status),
                        "quality_score": target_product.quality_score,
                        "attributes": [
                            {
                                "name": a.attribute_name,
                                "raw_value": a.raw_value,
                                "normalized_value": a.normalized_value,
                                "unit": a.unit,
                                "confidence": a.confidence,
                                "evidence": evidence_map.get(str(a.id)),
                            }
                            for a in attrs
                        ],
                        "open_validation_issues": [
                            {
                                "validation_type": str(v.validation_type.value if hasattr(v.validation_type, "value") else v.validation_type),
                                "severity": str(v.severity.value if hasattr(v.severity, "value") else v.severity),
                                "message": v.message,
                                "actual_value": v.actual_value,
                            }
                            for v in vals
                        ],
                    }
        except Exception as e:
            logger.debug(f"Could not augment assistant product context: {e}")

        try:
            res_dict = self.provider.generate_assistant_response(
                message=raw_msg,
                history=history,
                context=enriched_context,
            )
            msg_text = (
                res_dict.get("message")
                or res_dict.get("reply")
                or res_dict.get("response")
                or res_dict.get("text")
                or ""
            ).strip()
            if not msg_text:
                msg_text = (
                    "CatalogIQ Assistant is available to help you navigate document parsing, "
                    "attribute extraction, confidence scoring, quality validation, multi-source reconciliation, "
                    "and 252-column catalog export."
                )
            return AssistantChatResponse(
                message=msg_text,
                reply=msg_text,
                suggestions=res_dict.get("suggestions", []),
            )
        except ConfigurationError as e:
            logger.error(f"LLM Provider configuration error in AssistantService: {e}")
            return AssistantChatResponse(
                message=(
                    "CatalogIQ Assistant AI features are temporarily unavailable. Operating in grounded mode. "
                    "You can ask about supported file formats (PDF, DOCX, XLSX, CSV, JSON, XML, HTML), "
                    "batch processing, AI commerce enrichment, human review, multi-source reconciliation, or 252-column export."
                ),
                suggestions=[
                    "What file formats does CatalogIQ support?",
                    "How does batch processing work?",
                    "What happens when I upload Excel?",
                ],
            )
        except Exception as e:
            logger.error(f"Assistant error processing question: {e}")
            return AssistantChatResponse(
                message=(
                    "CatalogIQ Assistant is available to assist you with document parsing, "
                    "attribute extraction, validation rules, multi-source reconciliation, and export delivery."
                ),
                suggestions=[
                    "What file formats does CatalogIQ support?",
                    "How is a product enriched?",
                    "What is Multi-Source Reconciliation?",
                ],
            )
