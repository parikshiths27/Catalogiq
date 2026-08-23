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

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        session: Optional[Any] = None,
    ):
        self._provider = provider
        self._session = session

    @property
    def provider(self) -> BaseLLMProvider:
        if self._provider is None:
            self._provider = get_llm_provider()
        return self._provider

    def _enrich_product_context(
        self,
        raw_msg: str,
        enriched_context: Dict[str, Any],
        session: Any,
    ) -> None:
        """
        Retrieves product facts from database if context or message references a product.
        """
        from sqlmodel import select
        from sqlalchemy import or_
        from app.models import Product, ProductAttribute, ValidationResult, ValidationStatus, AttributeEvidence
        import re
        import uuid

        target_product = None
        queried_identifier: Optional[str] = None

        # 1. Check if product_id or sku is in context
        if enriched_context.get("product_id"):
            try:
                p_uuid = uuid.UUID(str(enriched_context["product_id"]))
                target_product = session.get(Product, p_uuid)
                if target_product:
                    queried_identifier = target_product.sku or str(target_product.id)
            except Exception:
                pass

        if not target_product and enriched_context.get("sku"):
            sku_val = str(enriched_context["sku"]).strip()
            target_product = session.exec(
                select(Product).where(Product.sku.ilike(sku_val))
            ).first()
            if target_product:
                queried_identifier = sku_val

        # 2. If no product found from context, search message for product/SKU/MPN identifiers
        if not target_product:
            tokens_to_search: List[str] = []
            kw_match = re.search(
                r"(?:product|sku|mpn|part|model|item)\s+([A-Za-z0-9\-_./]+)",
                raw_msg,
                re.IGNORECASE,
            )
            if kw_match:
                cand = kw_match.group(1).strip().rstrip("?.!,:;")
                if len(cand) >= 2 and cand.lower() not in {"is", "the", "a", "an", "this", "that", "needs_review"}:
                    tokens_to_search.append(cand)
                    queried_identifier = cand

            # Check part-number like tokens (contains numbers, hyphens, or mixed alphanumeric)
            all_tokens = re.findall(r"\b[A-Za-z0-9\-_./]{3,}\b", raw_msg)
            for tok in all_tokens:
                clean_tok = tok.strip().rstrip("?.!,:;")
                has_digit = any(c.isdigit() for c in clean_tok)
                has_hyphen = "-" in clean_tok or "_" in clean_tok
                if (has_digit or has_hyphen) and clean_tok not in tokens_to_search:
                    tokens_to_search.append(clean_tok)
                    if not queried_identifier:
                        queried_identifier = clean_tok

            if tokens_to_search:
                exact_conds = []
                for cand in tokens_to_search[:5]:
                    exact_conds.append(Product.sku.ilike(cand))
                    exact_conds.append(Product.model.ilike(cand))
                target_product = session.exec(
                    select(Product).where(or_(*exact_conds))
                ).first()

                if not target_product:
                    partial_conds = []
                    for cand in tokens_to_search[:3]:
                        partial_conds.append(Product.sku.ilike(f"%{cand}%"))
                        partial_conds.append(Product.model.ilike(f"%{cand}%"))
                    target_product = session.exec(
                        select(Product).where(or_(*partial_conds))
                    ).first()

                if target_product:
                    queried_identifier = target_product.sku or tokens_to_search[0]

        if target_product:
            attrs = session.exec(
                select(ProductAttribute).where(ProductAttribute.product_id == target_product.id)
            ).all()
            vals = session.exec(
                select(ValidationResult).where(
                    ValidationResult.product_id == target_product.id,
                )
            ).all()
            evidences = session.exec(
                select(AttributeEvidence).where(
                    AttributeEvidence.attribute_id.in_([a.id for a in attrs])
                )
            ).all() if attrs else []

            source_ids = [ev.source_id for ev in evidences if ev.source_id]
            doc_ids = [ev.document_id for ev in evidences if ev.document_id]

            sources_by_id = {}
            if source_ids:
                from app.models import Source
                for s in session.exec(select(Source).where(Source.id.in_(source_ids))).all():
                    sources_by_id[s.id] = s

            docs_by_id = {}
            if doc_ids:
                from app.models import Document
                for d in session.exec(select(Document).where(Document.id.in_(doc_ids))).all():
                    docs_by_id[d.id] = d

            evidence_map = {}
            for ev in evidences:
                src_obj = sources_by_id.get(ev.source_id) if ev.source_id else None
                doc_obj = docs_by_id.get(ev.document_id) if ev.document_id else None
                src_name = src_obj.name if src_obj else (doc_obj.filename if doc_obj else "Catalog Document")

                evidence_map[str(ev.attribute_id)] = {
                    "source_name": src_name,
                    "source_type": str(src_obj.source_type.value if src_obj and hasattr(src_obj.source_type, "value") else (str(src_obj.source_type) if src_obj else "document")),
                    "trust_level": src_obj.trust_level if src_obj else 1.0,
                    "document_filename": doc_obj.filename if doc_obj else None,
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
                "subcategory": target_product.subcategory,
                "product_type": target_product.product_type,
                "status": str(target_product.status.value if hasattr(target_product.status, "value") else target_product.status),
                "quality_score": target_product.quality_score,
                "commerce_description": target_product.commerce_description or target_product.description,
                "features": target_product.features or [],
                "applications": target_product.applications or [],
                "attributes": [
                    {
                        "name": a.attribute_name,
                        "display_name": a.display_name or a.attribute_name,
                        "raw_value": a.raw_value,
                        "normalized_value": a.normalized_value,
                        "unit": a.unit,
                        "confidence": a.confidence,
                        "status": str(a.status.value if hasattr(a.status, "value") else a.status),
                        "source_type": a.source_type,
                        "evidence": evidence_map.get(str(a.id)),
                    }
                    for a in attrs
                ],
                "open_validation_issues": [
                    {
                        "validation_type": str(v.validation_type.value if hasattr(v.validation_type, "value") else v.validation_type),
                        "severity": str(v.severity.value if hasattr(v.severity, "value") else v.severity),
                        "status": str(v.status.value if hasattr(v.status, "value") else v.status),
                        "message": v.message,
                        "actual_value": v.actual_value,
                        "expected_value": v.expected_value,
                    }
                    for v in vals
                    if v.status == ValidationStatus.open
                ],
                "validation_issues": [
                    {
                        "validation_type": str(v.validation_type.value if hasattr(v.validation_type, "value") else v.validation_type),
                        "severity": str(v.severity.value if hasattr(v.severity, "value") else v.severity),
                        "status": str(v.status.value if hasattr(v.status, "value") else v.status),
                        "message": v.message,
                        "actual_value": v.actual_value,
                        "expected_value": v.expected_value,
                    }
                    for v in vals
                ],
            }
            enriched_context["product_search"] = {
                "queried_identifier": queried_identifier or target_product.sku,
                "found": True,
                "sku": target_product.sku,
            }
        elif queried_identifier:
            enriched_context["product_search"] = {
                "queried_identifier": queried_identifier,
                "found": False,
            }

    def answer_question(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
        session: Optional[Any] = None,
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
            active_session = session or self._session
            if active_session:
                self._enrich_product_context(raw_msg, enriched_context, active_session)
            else:
                from app.db.session import engine
                from sqlmodel import Session
                with Session(engine) as db_sess:
                    self._enrich_product_context(raw_msg, enriched_context, db_sess)
        except Exception as e:
            logger.warning(f"Could not augment assistant product context: {e}", exc_info=True)

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
