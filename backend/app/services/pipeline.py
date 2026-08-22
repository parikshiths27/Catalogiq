"""
CatalogIQ extraction pipeline — core stage implementations.

Architecture:
  - TableExtractor:     Deterministic extraction from structured Docling tables.
  - ExtractionStage:    Full AI extraction pipeline stage (extends PipelineStage).
  - ConflictDetector:   Compares new attributes against existing DB values.

Data flow through ExtractionStage:
  Docling IR
       ↓
  +----+----+
  |         |
  Tables   Text
  |         |
  Det.    LLM Provider
  Parse   (Ollama/Gemini/Mock)
  |         |
  +----+----+
       ↓
  Merged Candidate Data
       ↓
  Normalization (AttributeNormalizer)
       ↓
  Evidence Verification (EvidenceResolver)
       ↓
  Confidence Scoring (ConfidenceCalculator)
       ↓
  Conflict Detection (ConflictDetector)
       ↓
  ProductService (upsert or create Product)
       ↓
  AttributeRepository (persist attributes + evidence)
       ↓
  CacheService (register extraction cache entry)
       ↓
  PostgreSQL
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session, select

from app.core.config import settings
from app.models import (
    AttributeDataType,
    AttributeEvidence,
    AttributeStatus,
    CacheType,
    Document,
    DocumentStatus,
    EnrichmentResult,
    EnrichmentStatus,
    EnrichmentType,
    JobStatus,
    ProcessingJob,
    ProcessingStep,
    ProcessingStage,
    Product,
    ProductAttribute,
    ProductDocumentAssociation,
    ProductStatus,
    Source,
    SourceType,
    StepStatus,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
    ValidationType,
)
from app.repositories import AttributeRepository, ProductRepository
from app.services.cache import CacheService
from app.services.confidence import ConfidenceCalculator
from app.services.document import DocumentService
from app.services.evidence_resolver import EvidenceResolver
from app.services.llm.base import ExtractionResult, RawAttributeItem
from app.services.normalizer import AttributeNormalizer, repair_mojibake
from app.services.parser import DocumentParser, MultiFormatParser, DoclingParser
from app.services.product import ProductService
from app.services.storage import get_storage_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error types (re-exported from Phase 3 for worker compatibility)
# ---------------------------------------------------------------------------

class ProcessingError(Exception):
    pass


class TransientProcessingError(ProcessingError):
    """Errors that can be retried (e.g., storage timeout, Redis network glitches)."""
    pass


class NonRetryableProcessingError(ProcessingError):
    """Errors that should fail immediately (e.g., corrupted PDF, empty file)."""
    pass


class ExtractionConfigurationError(NonRetryableProcessingError):
    """Raised when the LLM provider is misconfigured — non-retryable."""
    pass


# ---------------------------------------------------------------------------
# Pipeline stage base class
# ---------------------------------------------------------------------------

class PipelineStage(ABC):
    @abstractmethod
    def execute(
        self,
        session: Session,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Phase 3: ParsingStage (MultiFormatParser handles PDF, CSV, Excel, XML, JSON)
# ---------------------------------------------------------------------------

class ParsingStage(PipelineStage):
    def __init__(self, parser: Optional[DocumentParser] = None):
        # Default to MultiFormatParser to seamlessly handle CSV, Excel, PDF, JSON, XML
        self.parser = parser or MultiFormatParser()

    def execute(self, session: Session, document_id: uuid.UUID, job_id: uuid.UUID, step_id: uuid.UUID) -> None:
        document = session.get(Document, document_id)
        if not document:
            raise NonRetryableProcessingError(f"Document with ID {document_id} not found")

        job = session.get(ProcessingJob, job_id)
        if not job:
            raise NonRetryableProcessingError(f"Job with ID {job_id} not found")

        step = session.get(ProcessingStep, step_id)
        if not step:
            raise NonRetryableProcessingError(f"Step with ID {step_id} not found")

        # 1. Update DB statuses to processing
        now = datetime.now(timezone.utc)
        step.status = StepStatus.processing
        step.started_at = now
        step.updated_at = now

        job.status = JobStatus.processing
        job.started_at = now
        job.current_stage = "parsing"
        job.updated_at = now

        document.status = DocumentStatus.parsing
        document.updated_at = now

        session.add(step)
        session.add(job)
        session.add(document)
        session.commit()

        # 2. Check for cache hits: file_hash + parser_name + parser_version
        parser_name = self.parser.__class__.__name__
        parser_version = getattr(self.parser, "version", "1.0.0")

        cache_service = CacheService(session)
        cache_key = f"cache:parse:{document.file_hash}:{parser_name}:{parser_version}"

        cached_storage_key = cache_service.get_cache(cache_key)
        storage = get_storage_service()

        if cached_storage_key:
            # Cache Hit! Reuse parsed output from object storage
            logger.info(f"Cache hit for key {cache_key}. Reusing parsed document output.")
            try:
                parsed_bytes = storage.download_file(cached_storage_key)
                parsed_data = json.loads(parsed_bytes.decode("utf-8"))
                content_hash = parsed_data.get("content_hash")

                # Apply cached data to Document record
                document.status = DocumentStatus.processed
                document.content_hash = content_hash
                document.parsed_storage_key = cached_storage_key
                document.parser_name = parser_name
                document.parser_version = parser_version
                document.page_count = len(parsed_data.get("pages", []))
                document.parsed_at = datetime.now(timezone.utc)
                document.updated_at = datetime.now(timezone.utc)

                step.status = StepStatus.completed
                step.completed_at = datetime.now(timezone.utc)
                step.updated_at = datetime.now(timezone.utc)

                job.status = JobStatus.processing  # still processing (extraction next)
                job.completed_items = 1
                job.updated_at = datetime.now(timezone.utc)

                session.add(document)
                session.add(step)
                session.add(job)
                session.commit()
                return
            except Exception as e:
                logger.warning(f"Failed to read cached parsed document: {e}. Falling back to parsing.")

        # 3. Cache Miss - Fetch original file and parse
        try:
            file_bytes = storage.download_file(document.storage_key)
        except Exception as e:
            raise TransientProcessingError(f"Failed to download original document from store: {e}")

        # 4. Invoke the parser
        try:
            try:
                parsed_data = self.parser.parse(file_bytes, filename=document.filename)
            except TypeError:
                parsed_data = self.parser.parse(file_bytes)
        except ValueError as e:
            raise NonRetryableProcessingError(f"Document format error: {e}")
        except Exception as e:
            raise NonRetryableProcessingError(f"Document parsing failed: {e}")

        # 5. Add document tracking context to representation
        parsed_data["document_id"] = str(document_id)
        parsed_data["parser"] = {
            "name": parser_name,
            "version": parser_version
        }

        # 6. Normalize and calculate deterministic content hash (sorting keys)
        normalized_str = json.dumps(parsed_data, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(normalized_str.encode("utf-8")).hexdigest()
        parsed_data["content_hash"] = content_hash

        # 7. Upload parsed output to storage
        parsed_storage_key = f"documents/parsed/{document_id}.json"
        try:
            storage.upload_file(
                json.dumps(parsed_data, indent=2).encode("utf-8"),
                parsed_storage_key
            )
        except Exception as e:
            raise TransientProcessingError(f"Failed to store parsed representation in storage: {e}")

        # 8. Update database states
        document.status = DocumentStatus.processed
        document.content_hash = content_hash
        document.parsed_storage_key = parsed_storage_key
        document.parser_name = parser_name
        document.parser_version = parser_version
        document.page_count = len(parsed_data["pages"])
        document.parsed_at = datetime.now(timezone.utc)
        document.updated_at = datetime.now(timezone.utc)

        step.status = StepStatus.completed
        step.completed_at = datetime.now(timezone.utc)
        step.updated_at = datetime.now(timezone.utc)

        job.status = JobStatus.processing  # Extraction stage is next
        job.completed_items = 1
        job.updated_at = datetime.now(timezone.utc)

        # 9. Register cache entry
        cache_service.set_cache(
            cache_key=cache_key,
            cache_type=CacheType.document,
            input_hash=document.file_hash,
            result_reference=parsed_storage_key,
            model=parser_name,
            prompt_version=parser_version,
            schema_version="v1",
            pipeline_version=settings.PIPELINE_VERSION,
        )

        session.add(document)
        session.add(step)
        session.add(job)
        session.commit()


# ---------------------------------------------------------------------------
# Phase 4: TableExtractor — deterministic structured table parsing
# ---------------------------------------------------------------------------

class TableExtractor:
    """
    Extracts ProductAttribute candidates from structured Docling IR tables.

    Strategy:
      - A 2-column table with a key-value structure is treated as a spec sheet.
      - Other table shapes are skipped (handled by LLM for context).
      - Extracts with extraction_method = "deterministic" and confidence based
        on table structure quality (2 clear columns = highest deterministic signal).

    This runs before the LLM — its output is merged into ExtractionResult.attributes.
    """

    def extract_from_ir(self, ir: Dict[str, Any]) -> List[RawAttributeItem]:
        """
        Scan all IR tables for key-value pairs and produce RawAttributeItem instances.

        Args:
            ir: The Docling Intermediate Representation.

        Returns:
            List of RawAttributeItem instances with extraction_method="deterministic".
        """
        items: List[RawAttributeItem] = []
        pages = ir.get("pages", [])

        for page in pages:
            page_no = page.get("page_number", 1)
            for table in page.get("tables", []):
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                extracted = self._extract_from_table(headers, rows, page_no)
                items.extend(extracted)

        logger.info(f"TableExtractor: extracted {len(items)} deterministic attributes from IR tables")
        return items

    def _extract_from_table(
        self,
        headers: List[Any],
        rows: List[List[Any]],
        page_no: int,
    ) -> List[RawAttributeItem]:
        """
        Attempts to interpret a table as a key-value specification table.

        A table qualifies if:
          - It has exactly 2 columns (or 2 meaningful headers), OR
          - Headers look like "Specification/Parameter/Attribute" + "Value/Rating/Quantity"
        """
        items: List[RawAttributeItem] = []

        if not rows:
            return items

        # Identify key-value column structure
        key_col, val_col = self._find_key_value_columns(headers, rows)
        if key_col is None or val_col is None:
            return items  # Not a key-value table

        for row in rows:
            if len(row) <= max(key_col, val_col):
                continue

            key_raw = str(row[key_col]).strip()
            val_raw = str(row[val_col]).strip()

            if not key_raw or not val_raw or key_raw.lower() in {"", "n/a", "-", "—"}:
                continue

            # Skip rows where key looks like a header repeat
            if key_raw.lower() in {str(h).lower() for h in headers}:
                continue

            # Canonicalize attribute name
            attr_name = self._canonicalize_name(key_raw)
            if not attr_name:
                continue

            # Build evidence_text from the row
            evidence_text = f"{key_raw} | {val_raw}"

            # Infer data_type from value
            data_type, unit = self._infer_type_and_unit(val_raw)

            item = RawAttributeItem(
                name=attr_name,
                display_name=key_raw,
                raw_value=val_raw,
                unit=unit,
                data_type=data_type,
                evidence_text=evidence_text,
                page_number=page_no,
                extraction_method="deterministic",
                evidence_verified=False,  # EvidenceResolver will verify
                llm_confidence=0.88,      # Default for deterministic — not 1.0
            )
            items.append(item)

        return items

    def _find_key_value_columns(
        self, headers: List[Any], rows: List[List[Any]]
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Identifies which column is the "attribute name" and which is the "value".
        Returns (key_col_index, value_col_index) or (None, None) if unclear.
        """
        # If no headers provided, check row widths
        if not headers:
            # Check if rows consistently have 2 columns
            row_widths = [len(r) for r in rows[:5] if r]
            if row_widths and max(row_widths) == 2:
                return 0, 1
            return None, None

        # 2-column table is the clearest signal
        if len(headers) == 2:
            return 0, 1

        # Look for header keywords suggesting key-value
        _KEY_HEADERS = {"specification", "parameter", "attribute", "property", "feature", "item", "name"}
        _VAL_HEADERS = {"value", "rating", "quantity", "measurement", "reading", "data", "specification"}

        key_col = None
        val_col = None
        for i, h in enumerate(headers):
            h_lower = str(h).strip().lower()
            if h_lower in _KEY_HEADERS and key_col is None:
                key_col = i
            if h_lower in _VAL_HEADERS and val_col is None:
                val_col = i

        if key_col is not None and val_col is not None and key_col != val_col:
            return key_col, val_col

        return None, None

    def _canonicalize_name(self, display_name: str) -> str:
        """Convert 'Rated Voltage (AC)' → 'rated_voltage_ac' for attribute_name."""
        import re
        # Remove parenthetical content but keep text
        name = re.sub(r"\(.*?\)", "", display_name)
        # Remove special characters, lowercase, replace spaces with underscores
        name = re.sub(r"[^a-zA-Z0-9\s_]", "", name)
        name = re.sub(r"\s+", "_", name.strip().lower())
        name = re.sub(r"_+", "_", name).strip("_")
        return name

    def _infer_type_and_unit(self, value: str) -> Tuple[str, Optional[str]]:
        """
        Heuristically infer data_type and unit from a raw value string.
        Returns (data_type, unit).
        """
        import re
        value = value.strip()

        # Boolean
        if value.lower() in {"yes", "no", "true", "false"}:
            return "boolean", None

        # Numeric with unit — e.g., "230 V", "5.5kW", "1440 RPM"
        m = re.match(r"^[+-]?\d+(?:[.,]\d+)?\s*([a-zA-Z°%/]+)?$", value)
        if m:
            unit_str = (m.group(1) or "").strip() or None
            return "numeric", unit_str

        # Range values like "220-240 V" — still numeric context
        if re.match(r"^\d+[-–]\d+\s*[a-zA-Z°%]*$", value):
            return "numeric", None

        return "text", None


# ---------------------------------------------------------------------------
# Phase 4: ConflictDetector
# ---------------------------------------------------------------------------

class ConflictDetector:
    """
    Compares a newly extracted attribute value against existing DB values.

    Policy (per Phase 4 corrections):
      - Never silently overwrite an existing attribute even if new confidence is higher.
      - A meaningful value difference triggers a ValidationResult record.
      - Both values are preserved: the new one is added as a new row; the existing
        one is marked AttributeStatus.conflicting.
      - Human resolution handles which value to accept.

    A conflict is defined as: same attribute_name, different normalized_value,
    both non-trivial values (not empty/None).
    """

    def __init__(self, attr_repo: AttributeRepository) -> None:
        self._attr_repo = attr_repo

    def check_and_register(
        self,
        product_id: uuid.UUID,
        attribute_name: str,
        new_raw_value: str,
        new_confidence: float,
    ) -> Tuple[bool, int]:
        """
        Check for conflicts with existing attributes for this product + name.

        Returns:
            (has_conflict: bool, conflict_count: int)

        Side effect:
            Marks existing conflicting attributes as AttributeStatus.conflicting.
        """
        existing = self._attr_repo.get_all_attributes_for_name(product_id, attribute_name)
        conflicts = 0

        for ex in existing:
            if self._values_conflict(ex.raw_value, new_raw_value):
                conflicts += 1
                # Mark existing as conflicting for human review
                if ex.status not in (AttributeStatus.conflicting, AttributeStatus.needs_review):
                    ex.status = AttributeStatus.conflicting
                    ex.updated_at = datetime.now(timezone.utc)
                    self._attr_repo.session.add(ex)

                # Create a ValidationResult for the conflict
                self._attr_repo.create_conflict_validation(
                    product_id=product_id,
                    attribute_id=ex.id,
                    existing_value=ex.raw_value,
                    new_value=new_raw_value,
                    existing_confidence=ex.confidence,
                    new_confidence=new_confidence,
                )

        if conflicts:
            self._attr_repo.session.commit()

        return conflicts > 0, conflicts

    def _values_conflict(self, existing: str, new: str) -> bool:
        """
        Returns True if the two raw values are meaningfully different.
        Ignores trivial differences (whitespace, case, trailing units).
        """
        def normalize(v: str) -> str:
            return " ".join(v.strip().lower().split())

        return normalize(existing) != normalize(new)


# ---------------------------------------------------------------------------
# Phase 4: ExtractionStage
# ---------------------------------------------------------------------------

class ExtractionStage(PipelineStage):
    """
    Full AI extraction pipeline stage.

    Orchestrates:
      1. TableExtractor  — deterministic structured extraction
      2. LLM Provider    — semantic extraction (injected via constructor)
      3. EvidenceResolver — evidence verification against IR
      4. AttributeNormalizer — type parsing and unit standardization
      5. ConfidenceCalculator — multi-factor 0–100 scoring
      6. ConflictDetector — conflict registration without overwriting
      7. ProductService  — product upsert
      8. AttributeRepository — attribute + evidence persistence
      9. CacheService    — extraction cache entry registration
    """

    def __init__(self, llm_provider=None) -> None:
        """
        Args:
            llm_provider: A BaseLLMProvider instance. If None, instantiated from settings.
                          Inject MockProvider in tests; leave None in production to use factory.
        """
        self._llm_provider = llm_provider  # Lazy-initialize to avoid import at module load

    def _get_provider(self):
        if self._llm_provider is None:
            from app.services.llm.factory import get_llm_provider
            self._llm_provider = get_llm_provider()
        return self._llm_provider

    def execute(
        self,
        session: Session,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        # ---- 1. Load entities ----
        document = session.get(Document, document_id)
        if not document:
            raise NonRetryableProcessingError(f"Document {document_id} not found")
        job = session.get(ProcessingJob, job_id)
        if not job:
            raise NonRetryableProcessingError(f"Job {job_id} not found")
        step = session.get(ProcessingStep, step_id)
        if not step:
            raise NonRetryableProcessingError(f"Step {step_id} not found")

        if not document.parsed_storage_key or not document.content_hash:
            raise NonRetryableProcessingError(
                f"Document {document_id} has no parsed output. "
                f"Ensure ParsingStage completed successfully before ExtractionStage."
            )

        # ---- 2. Update status ----
        now = datetime.now(timezone.utc)
        step.status = StepStatus.processing
        step.started_at = now
        step.updated_at = now
        job.current_stage = ProcessingStage.extracting
        job.updated_at = now
        session.add(step)
        session.add(job)
        session.commit()

        # ---- 3. Load parsed IR from storage ----
        storage = get_storage_service()
        try:
            ir_bytes = storage.download_file(document.parsed_storage_key)
            ir = json.loads(ir_bytes.decode("utf-8"))
        except Exception as e:
            raise TransientProcessingError(f"Failed to load parsed IR from storage: {e}")

        # ---- 4. Check extraction cache ----
        provider = self._get_provider()
        cache_service = CacheService(session)

        raw_cache_key = (
            f"{document.content_hash}:"
            f"{settings.EXTRACTION_SCHEMA_VERSION}:"
            f"{provider.model_name}:"
            f"{provider.prompt_version}"
        )
        cache_key = f"cache:ext:{hashlib.sha256(raw_cache_key.encode()).hexdigest()}"

        cached_ref = cache_service.get_cache(cache_key)
        if cached_ref:
            logger.info(
                f"Extraction cache hit for document {document_id} "
                f"(model={provider.model_name}, prompt={provider.prompt_version}). "
                f"Re-normalizing existing product attributes and marking step as completed."
            )
            self._reprocess_existing_attributes(session, document_id)
            self._complete_step_and_job(session, step, job)
            return

        # ---- Check if document is a tabular catalog dataset (Excel / CSV with product rows) ----
        is_tabular_catalog = False
        catalog_tables = []

        for page in ir.get("pages", []):
            for table in page.get("tables", []):
                headers = [str(h).strip().lstrip("\ufeff").lower() for h in table.get("headers", []) if str(h).strip()]
                rows = table.get("rows", [])
                if not rows:
                    continue
                catalog_kw = {
                    "mfg_part_num", "part_desc", "e1_brand", "unilog_brand", "dib_brand",
                    "part_manuf", "sku", "mpn", "part number", "part_number", "product name",
                    "product_name", "brand", "manufacturer", "description", "item", "title",
                    "dept", "class", "fine", "model"
                }
                headers_str = " ".join(headers)
                if any(kw in headers_str for kw in catalog_kw) or (
                    document.filename and document.filename.lower().endswith((".xlsx", ".xls", ".csv")) and len(headers) >= 2
                ):
                    is_tabular_catalog = True
                    catalog_tables.append(table)

        if is_tabular_catalog and catalog_tables:
            logger.info(
                f"ExtractionStage: Document {document_id} identified as tabular catalog. "
                f"Processing rows via Unilog EnrichmentPipeline."
            )
            from app.services.enrichment.pipeline import EnrichmentPipeline
            from app.services.llm.prompts import ENRICHMENT_PROMPT_VERSION
            from app.models import (
                EnrichmentResult,
                EnrichmentType,
                EnrichmentStatus,
                ValidationResult,
                ValidationType,
                ValidationSeverity,
                ValidationStatus,
            )

            enrichment_pipe = EnrichmentPipeline()
            product_service = ProductService(session)
            product_repo = ProductRepository(session)
            attr_repo = AttributeRepository(session)
            source = self._get_or_create_source(session, document)

            created_count = 0
            created_product_ids = []

            for table in catalog_tables:
                raw_headers = [str(h).strip().lstrip("\ufeff") for h in table.get("headers", [])]
                for row_vals in table.get("rows", []):
                    if not any(str(v).strip() for v in row_vals):
                        continue
                    row_dict = {h: str(v).strip() for h, v in zip(raw_headers, row_vals) if h}

                    # Ensure row contains a recognizable product identifier or description
                    has_identifier = any(
                        bool(row_dict.get(k, "").strip())
                        for k in [
                            "Mfg_Part_Num", "SKU", "Part Number", "Part_Number", "MPN",
                            "Part_Desc", "Product Name", "Product_Name", "Description", "Item", "Title"
                        ]
                    )
                    if not has_identifier and not any(len(str(v).strip()) > 3 for v in row_vals):
                        continue

                    enrich_res = enrichment_pipe.process_row(row_dict)

                    canonical_mpn = (
                        enrich_res["identity"]["mpn"]
                        or row_dict.get("Mfg_Part_Num")
                        or row_dict.get("SKU")
                        or row_dict.get("Part Number")
                        or row_dict.get("Part_Number")
                        or f"SKU-{uuid.uuid4().hex[:8]}"
                    )
                    canonical_brand = (
                        enrich_res["identity"]["brand"]
                        or row_dict.get("Brand")
                        or row_dict.get("Unilog_Brand")
                        or row_dict.get("Part_Manuf")
                        or "Industrial"
                    )
                    product_name = (
                        enrich_res["descriptions"]["short_desc"]
                        or enrich_res["taxonomy"]["product_name"]
                        or row_dict.get("Part_Desc")
                        or row_dict.get("Product Name")
                        or canonical_mpn
                    )

                    dept = enrich_res["taxonomy"]["dept"]
                    class_ = enrich_res["taxonomy"]["class"]
                    fine = enrich_res["taxonomy"]["fine"]
                    category = class_ or dept or enrich_res["taxonomy"]["classpath"] or "Industrial Equipment"
                    short_desc = enrich_res["descriptions"]["short_desc"] or row_dict.get("Part_Desc")
                    long_desc = enrich_res["descriptions"]["long_desc"] or short_desc
                    val_data = enrich_res["validation"]
                    quality_score = float(val_data.get("quality_score", 85.0))
                    is_verified = val_data.get("is_verified", False)

                    features = [
                        attr["normalized_value"]
                        for attr in enrich_res["attributes"]
                        if attr.get("name") in ["feature", "features", "mounting", "series", "with"]
                    ]
                    if not features and short_desc:
                        features = [short_desc]

                    prod_payload = {
                        "sku": canonical_mpn,
                        "brand": canonical_brand,
                        "product_name": product_name,
                        "model": canonical_mpn,
                        "category": category,
                        "subcategory": fine,
                        "description": short_desc,
                        "commerce_description": long_desc,
                        "features": features,
                        "applications": [category],
                        "quality_score": quality_score,
                        "status": ProductStatus.verified if is_verified else ProductStatus.needs_review,
                        "attributes": {},
                    }

                    existing = product_repo.get_by_sku_brand(sku=canonical_mpn, brand=canonical_brand)
                    if existing:
                        product = product_service.update_product(
                            product_id=existing.id,
                            updated_data=prod_payload,
                            change_summary=f"Catalog extraction from document {document_id}",
                            actor_type="ai",
                        )
                    else:
                        product = product_service.create_product(
                            product_data=prod_payload,
                            actor_type="ai",
                        )

                    self._associate_document(session, product.id, document_id)
                    created_count += 1
                    created_product_ids.append(product.id)

                    # Persist extracted attributes & evidence
                    for attr_item in enrich_res["attributes"]:
                        attr_name = attr_item.get("name") or attr_item.get("label") or "attribute"
                        disp_name = attr_item.get("label") or attr_name
                        norm_val = attr_item.get("normalized_value")
                        raw_val = attr_item.get("raw_value") or str(norm_val)
                        unit_val = attr_item.get("unit")
                        attr_conf = float(attr_item.get("confidence", 0.95))

                        db_attr = ProductAttribute(
                            product_id=product.id,
                            attribute_name=attr_name.lower().replace(" ", "_"),
                            display_name=disp_name,
                            raw_value=str(raw_val),
                            normalized_value=norm_val,
                            unit=unit_val,
                            data_type=AttributeDataType.text if not isinstance(norm_val, (int, float)) else AttributeDataType.numeric,
                            confidence=attr_conf,
                            status=AttributeStatus.verified if is_verified else AttributeStatus.needs_review,
                            source_type="document",
                        )
                        db_attr = attr_repo.upsert_attribute(db_attr)

                        evidence = AttributeEvidence(
                            attribute_id=db_attr.id,
                            source_id=source.id,
                            document_id=document_id,
                            page_number=1,
                            evidence_text=attr_item.get("evidence") or str(raw_val),
                            bbox_metadata={},
                            extraction_method="deterministic",
                        )
                        attr_repo.upsert_evidence(evidence)

                    # Persist EnrichmentResult with 5-channel descriptions and full 252-column delivery record
                    enrich_payload = {
                        "invoice_desc": enrich_res["descriptions"]["invoice_desc"],
                        "mobile_desc": enrich_res["descriptions"]["mobile_desc"],
                        "short_desc": enrich_res["descriptions"]["short_desc"],
                        "long_desc": enrich_res["descriptions"]["long_desc"],
                        "retail_desc": enrich_res["descriptions"]["retail_desc"],
                        "commerce_description": long_desc,
                        "features": features,
                        "applications": [category],
                        "confidence": quality_score / 100.0,
                        "delivery_record": enrich_res.get("delivery_record", {}),
                        "evidence_summary": enrich_res.get("evidence_summary", []),
                    }

                    old_enrich = session.exec(select(EnrichmentResult).where(EnrichmentResult.product_id == product.id)).all()
                    for oe in old_enrich:
                        session.delete(oe)

                    enrich_db = EnrichmentResult(
                        product_id=product.id,
                        enrichment_type=EnrichmentType.description,
                        generated_value=json.dumps(enrich_payload),
                        model="unilog-enrichment-engine-v1.0",
                        prompt_version=ENRICHMENT_PROMPT_VERSION,
                        confidence=quality_score / 100.0,
                        status=EnrichmentStatus.completed,
                    )
                    session.add(enrich_db)

                    # Clear existing open validation issues for this product to prevent duplicates
                    old_vals = session.exec(select(ValidationResult).where(ValidationResult.product_id == product.id)).all()
                    for ov in old_vals:
                        session.delete(ov)

                    # Persist specific ValidationResult records with explicit review reasons
                    for issue_item in val_data.get("issues", []):
                        if isinstance(issue_item, dict):
                            itype = issue_item.get("issue_type", "invalid_value")
                            imsg = issue_item.get("message", "Validation issue")
                            isev = issue_item.get("severity", "warning")
                            iexp = issue_item.get("expected_value")
                            iact = issue_item.get("actual_value")
                        else:
                            itype = "invalid_value"
                            imsg = str(issue_item)
                            isev = "warning"
                            iexp = None
                            iact = None

                        # Map issue_type string to ValidationType enum
                        val_enum_map = {
                            "manufacturer_unresolved": ValidationType.manufacturer_unresolved,
                            "unapproved_manufacturer": ValidationType.manufacturer_unresolved,
                            "brand_unresolved": ValidationType.brand_unresolved,
                            "unapproved_brand": ValidationType.brand_unresolved,
                            "taxonomy_unresolved": ValidationType.taxonomy_unresolved,
                            "unknown_classpath": ValidationType.taxonomy_unresolved,
                            "unsupported_uom": ValidationType.unsupported_uom,
                            "unapproved_uom": ValidationType.unsupported_uom,
                            "attribute_not_in_lov": ValidationType.attribute_not_in_lov,
                            "unsupported_claim": ValidationType.unsupported_claim,
                            "unsupported_claims": ValidationType.unsupported_claim,
                            "missing_required_attribute": ValidationType.missing_required_attribute,
                            "missing_required": ValidationType.missing_required_attribute,
                            "low_confidence": ValidationType.low_confidence,
                            "invalid_value": ValidationType.invalid_value,
                            "length_exceeded": ValidationType.invalid_value,
                            "casing_violation": ValidationType.invalid_value,
                        }
                        mapped_vtype = val_enum_map.get(itype, ValidationType.invalid_value)
                        mapped_sev = ValidationSeverity.error if isev == "error" else ValidationSeverity.warning

                        val_db = ValidationResult(
                            product_id=product.id,
                            validation_type=mapped_vtype,
                            severity=mapped_sev,
                            status=ValidationStatus.open,
                            message=imsg,
                            expected_value=iexp,
                            actual_value=iact,
                        )
                        session.add(val_db)

            # Store extraction summary
            extraction_storage_key = f"documents/extracted/{document_id}.json"
            extraction_summary = {
                "document_id": str(document_id),
                "is_tabular_catalog": True,
                "products_count": created_count,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                storage.upload_file(
                    json.dumps(extraction_summary, indent=2).encode("utf-8"),
                    extraction_storage_key,
                )
            except Exception as e:
                logger.warning(f"Failed to upload extraction summary: {e}")

            now = datetime.now(timezone.utc)
            job.total_items = created_count
            job.completed_items = created_count
            job.status = JobStatus.completed
            job.current_stage = ProcessingStage.completed
            job.completed_at = now
            job.updated_at = now

            step.status = StepStatus.completed
            step.completed_at = now
            step.updated_at = now

            document.status = DocumentStatus.processed
            document.updated_at = now

            session.add(document)
            session.add(step)
            session.add(job)
            session.commit()

            from app.workers.tasks.document_processing import _update_batch_progress_if_needed
            _update_batch_progress_if_needed(session, document)

            logger.info(f"ExtractionStage: successfully enriched and persisted {created_count} products from tabular document {document_id}")
            return

        # ---- 5. Deterministic table extraction (for prose/PDF docs) ----
        table_extractor = TableExtractor()
        table_attrs = table_extractor.extract_from_ir(ir)

        # ---- 6. LLM semantic extraction ----
        try:
            llm_result: ExtractionResult = provider.extract(ir)
        except Exception as e:
            from app.services.llm.base import ConfigurationError
            if isinstance(e, ConfigurationError):
                raise ExtractionConfigurationError(str(e)) from e
            err_str = str(e).lower()
            if any(k in err_str for k in ["429", "503", "resource_exhausted", "quota exceeded", "retry in"]):
                raise TransientProcessingError(f"Transient LLM extraction failure: {e}") from e
            raise NonRetryableProcessingError(f"LLM extraction failed: {e}") from e

        # ---- 7. Merge: table attrs take precedence (deterministic first) ----
        det_names = {a.name for a in table_attrs}
        merged_attrs: List[RawAttributeItem] = list(table_attrs)
        for attr in llm_result.attributes:
            if attr.name not in det_names:
                merged_attrs.append(attr)
        llm_result.attributes = merged_attrs

        # ---- 8. Evidence resolution ----
        resolver = EvidenceResolver()
        llm_result = resolver.resolve(llm_result, ir)

        # ---- 9. Normalization ----
        normalizer = AttributeNormalizer()
        confidence_calc = ConfidenceCalculator()

        # ---- 10. Create / find Source record for this document ----
        source = self._get_or_create_source(session, document)

        # ---- 11. Upsert Product ----
        product_service = ProductService(session)
        product_repo = ProductRepository(session)
        product_data = self._build_product_data(llm_result)

        existing_product = product_repo.get_by_sku_brand(
            sku=product_data.get("sku", ""),
            brand=product_data.get("brand", ""),
        )

        if existing_product:
            product = product_service.update_product(
                product_id=existing_product.id,
                updated_data=product_data,
                change_summary=f"AI extraction from document {document_id}",
                actor_type="ai",
            )
            logger.info(f"Updated existing product {product.id} ({product.brand} {product.sku})")
        else:
            product = product_service.create_product(
                product_data=product_data,
                actor_type="ai",
            )
            logger.info(f"Created new product {product.id} ({product.brand} {product.sku})")

        # Associate document with product
        self._associate_document(session, product.id, document_id)

        # ---- 12. Persist attributes + evidence ----
        attr_repo = AttributeRepository(session)
        conflict_detector = ConflictDetector(attr_repo)

        persisted_count = 0
        for attr_item in llm_result.attributes:
            try:
                repaired_raw = repair_mojibake(attr_item.raw_value)
                norm_result = normalizer.normalize(
                    raw_value=repaired_raw,
                    data_type=attr_item.data_type,
                    unit=attr_item.unit,
                )

                logger.info(
                    f"[Normalization Output] attr={attr_item.name}, raw={repaired_raw!r}, "
                    f"norm={norm_result.normalized_value!r}, data_type={norm_result.data_type}"
                )

                # Check for conflicts BEFORE scoring
                has_conflict, conflict_count = conflict_detector.check_and_register(
                    product_id=product.id,
                    attribute_name=attr_item.name,
                    new_raw_value=repaired_raw,
                    new_confidence=attr_item.llm_confidence,
                )

                # Calculate confidence
                conf_score = confidence_calc.calculate(
                    extraction_method=attr_item.extraction_method,
                    evidence_verified=attr_item.evidence_verified,
                    normalization_success=norm_result.success,
                    llm_confidence=attr_item.llm_confidence,
                    source_trust=source.trust_level,
                    conflict_count=conflict_count,
                )

                final_status = conf_score.status
                if has_conflict:
                    final_status = AttributeStatus.conflicting

                # Create and persist the attribute
                db_attr = ProductAttribute(
                    product_id=product.id,
                    attribute_name=attr_item.name,
                    display_name=attr_item.display_name,
                    raw_value=repaired_raw,
                    normalized_value=norm_result.normalized_value,
                    unit=norm_result.unit,
                    data_type=norm_result.data_type,
                    confidence=conf_score.to_pipeline_float(),
                    status=final_status,
                    source_type=attr_item.extraction_method,
                )

                db_attr = attr_repo.upsert_attribute(db_attr)

                # Create and persist evidence idempotently
                evidence = AttributeEvidence(
                    attribute_id=db_attr.id,
                    source_id=source.id,
                    document_id=document_id,
                    page_number=attr_item.page_number,
                    evidence_text=attr_item.evidence_text or attr_item.raw_value,
                    bbox_metadata={},
                    extraction_method=attr_item.extraction_method,
                )
                attr_repo.upsert_evidence(evidence)
                persisted_count += 1

            except Exception as attr_err:
                logger.error(
                    f"Failed to persist attribute '{attr_item.name}' for product {product.id}: {attr_err}",
                    exc_info=True,
                )

        session.commit()

        logger.info(
            f"ExtractionStage: persisted {persisted_count}/{len(llm_result.attributes)} "
            f"attributes for product {product.id}"
        )

        # ---- 13. Store extraction result in storage ----
        extraction_storage_key = f"documents/extracted/{document_id}.json"
        try:
            extraction_summary = {
                "document_id": str(document_id),
                "product_id": str(product.id),
                "provider": provider.provider_name,
                "model": provider.model_name,
                "prompt_version": provider.prompt_version,
                "schema_version": settings.EXTRACTION_SCHEMA_VERSION,
                "attributes_count": persisted_count,
                "extracted_at": now.isoformat(),
            }
            storage.upload_file(
                json.dumps(extraction_summary, indent=2).encode("utf-8"),
                extraction_storage_key,
            )
        except Exception as e:
            logger.warning(f"Failed to write extraction summary to storage: {e}")

        # ---- 14. Register extraction cache entry ----
        cache_service.set_cache(
            cache_key=cache_key,
            cache_type=CacheType.extraction,
            input_hash=document.content_hash,
            result_reference=extraction_storage_key,
            model=provider.model_name,
            prompt_version=provider.prompt_version,
            schema_version=settings.EXTRACTION_SCHEMA_VERSION,
            pipeline_version=settings.PIPELINE_VERSION,
        )

        # ---- 15. Mark step and job as completed ----
        self._complete_step_and_job(session, step, job)

    def _reprocess_existing_attributes(self, session: Session, document_id: uuid.UUID) -> None:
        """
        On extraction cache hit, re-normalizes existing ProductAttributes for the associated product
        so that updated normalizer rules (such as mojibake repair) are applied to existing DB records
        without needing to re-call the external LLM provider.
        """
        from sqlmodel import select
        from app.models import ProductDocumentAssociation, ProductAttribute
        from app.repositories import AttributeRepository

        stmt = select(ProductDocumentAssociation).where(ProductDocumentAssociation.document_id == document_id)
        assocs = session.exec(stmt).all()
        if not assocs:
            return

        attr_repo = AttributeRepository(session)
        normalizer = AttributeNormalizer()

        for assoc in assocs:
            attributes = attr_repo.list_by_product(assoc.product_id)
            for attr in attributes:
                repaired_raw = repair_mojibake(attr.raw_value)
                dt_str = getattr(attr.data_type, "value", str(attr.data_type))
                norm_result = normalizer.normalize(
                    raw_value=repaired_raw,
                    data_type=dt_str,
                    unit=attr.unit,
                )
                attr.raw_value = repaired_raw
                attr.normalized_value = norm_result.normalized_value
                attr.unit = norm_result.unit
                attr.updated_at = datetime.now(timezone.utc)
                session.add(attr)

        session.commit()

    def _complete_step_and_job(
        self, session: Session, step: ProcessingStep, job: ProcessingJob
    ) -> None:
        now = datetime.now(timezone.utc)
        step.status = StepStatus.completed
        step.completed_at = now
        step.updated_at = now
        job.status = JobStatus.completed
        job.completed_at = now
        job.updated_at = now
        session.add(step)
        session.add(job)
        session.commit()

    def _build_product_data(self, result: ExtractionResult) -> Dict[str, Any]:
        """Build a product dict from ExtractionResult for ProductService."""
        return {
            "sku": result.sku or "UNKNOWN",
            "brand": result.brand or "UNKNOWN",
            "product_name": result.product_name or "Unknown Product",
            "model": result.model_number,
            "category": result.category or "Uncategorized",
            "subcategory": result.subcategory,
            "product_type": result.product_type,
            "description": result.description,
            "features": result.features or [],
            "applications": result.applications or [],
            "certifications": result.certifications or [],
            "keywords": result.keywords or [],
            "attributes": {},
        }

    def _get_or_create_source(self, session: Session, document: Document) -> Source:
        """Get or create a Source record representing this document as provenance."""
        from sqlmodel import select
        stmt = select(Source).where(Source.document_id == document.id)
        existing = session.exec(stmt).first()
        if existing:
            return existing

        source = Source(
            id=uuid.uuid4(),
            name=document.filename or "Uploaded Document",
            source_type=SourceType.document,
            uri=document.storage_key,
            trust_level=0.9,
            document_id=document.id,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return source

    def _associate_document(
        self, session: Session, product_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Idempotently associate a document with a product."""
        from sqlmodel import select
        stmt = select(ProductDocumentAssociation).where(
            ProductDocumentAssociation.product_id == product_id,
            ProductDocumentAssociation.document_id == document_id,
        )
        existing = session.exec(stmt).first()
        if not existing:
            assoc = ProductDocumentAssociation(
                product_id=product_id,
                document_id=document_id,
                role="primary_specification",
            )
            session.add(assoc)
            session.commit()


# ---------------------------------------------------------------------------
# Phase 3: ValidationStage
# ---------------------------------------------------------------------------

class ValidationStage(PipelineStage):
    """
    Validation pipeline stage.
    Runs deterministic validation checks on all products extracted from the document.
    """

    def execute(
        self,
        session: Session,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        from sqlmodel import select
        from app.models import (
            Product,
            ProductDocumentAssociation,
            ProductStatus,
            ValidationResult,
            ValidationStatus,
        )
        from app.repositories import AttributeRepository
        from app.services.validation_engine import ValidationEngine

        # ---- 1. Load entities ----
        document = session.get(Document, document_id)
        if not document:
            raise NonRetryableProcessingError(f"Document {document_id} not found")
        job = session.get(ProcessingJob, job_id)
        if not job:
            raise NonRetryableProcessingError(f"Job {job_id} not found")
        step = session.get(ProcessingStep, step_id)
        if not step:
            raise NonRetryableProcessingError(f"Step {step_id} not found")

        # Find all associated products
        stmt = select(ProductDocumentAssociation).where(ProductDocumentAssociation.document_id == document_id)
        assocs = session.exec(stmt).all()

        if not assocs:
            raise NonRetryableProcessingError(f"No products associated with document {document_id}")

        # ---- 2. Update statuses ----
        now = datetime.now(timezone.utc)
        step.status = StepStatus.processing
        step.started_at = now
        step.updated_at = now
        job.current_stage = ProcessingStage.validating
        job.updated_at = now
        session.add(step)
        session.add(job)
        session.commit()

        attr_repo = AttributeRepository(session)
        engine = ValidationEngine()

        for assoc in assocs:
            product = session.get(Product, assoc.product_id)
            if not product:
                continue

            # Check if domain-specific validation already exists for this product (from EnrichmentPipeline)
            enrichment = session.exec(
                select(EnrichmentResult).where(
                    EnrichmentResult.product_id == product.id,
                    EnrichmentResult.status == EnrichmentStatus.completed,
                )
            ).first()

            if enrichment and "delivery_record" in (enrichment.generated_value or ""):
                # Authoritative domain LOV validation already established
                continue

            # ---- 3. Load product attributes & evidence ----
            attributes = attr_repo.list_by_product(product.id)
            evidence_list = attr_repo.get_evidence_for_product(product.id)

            evidence_names = {
                a.attribute_name for a in attributes
                if any(e.attribute_id == a.id and e.evidence_text for e in evidence_list)
            }

            # ---- 4. Run ValidationEngine ----
            val_res = engine.validate_product(
                product=product,
                attributes=attributes,
                evidence_supported_attribute_names=evidence_names,
                source_trust_level=0.9,
            )

            # ---- 5. Persist ValidationResult records idempotently ----
            existing_open = session.exec(
                select(ValidationResult).where(
                    ValidationResult.product_id == product.id,
                    ValidationResult.status == ValidationStatus.open,
                )
            ).all()
            for old in existing_open:
                session.delete(old)

            for issue in val_res.issues:
                db_res = issue.to_db_model(product.id)
                session.add(db_res)

            # ---- 6. Update Product quality_score & status ----
            product.quality_score = val_res.quality_breakdown.quality_score
            
            if val_res.has_critical_issues or val_res.has_errors or product.quality_score < 70.0:
                product.status = ProductStatus.needs_review
            else:
                product.status = ProductStatus.verified

            product.updated_at = now
            session.add(product)

        # ---- 7. Complete step ----
        step.status = StepStatus.completed
        step.completed_at = now
        step.updated_at = now
        job.status = JobStatus.processing
        job.updated_at = now

        session.add(step)
        session.add(job)
        session.commit()
        logger.info(f"ValidationStage completed for {len(assocs)} products from document {document_id}")


# ---------------------------------------------------------------------------
# Phase 5: EnrichmentStage
# ---------------------------------------------------------------------------

class EnrichmentStage(PipelineStage):
    """
    Enrichment pipeline stage.
    Ensures publication-grade commerce descriptions, bullet features, and search indexing for all products.
    """

    def __init__(self, llm_provider=None) -> None:
        self._llm_provider = llm_provider

    def _get_provider(self):
        if self._llm_provider is None:
            from app.services.llm.factory import get_llm_provider
            self._llm_provider = get_llm_provider()
        return self._llm_provider

    def execute(
        self,
        session: Session,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        from sqlmodel import select
        from app.models import (
            EnrichmentResult,
            EnrichmentStatus,
            EnrichmentType,
            Product,
            ProductDocumentAssociation,
        )
        from app.services.claim_checker import ClaimChecker
        from app.services.enrichment_confidence import EnrichmentConfidenceCalculator
        from app.services.llm.prompts import ENRICHMENT_PROMPT_VERSION

        # ---- 1. Load entities ----
        document = session.get(Document, document_id)
        if not document:
            raise NonRetryableProcessingError(f"Document {document_id} not found")
        job = session.get(ProcessingJob, job_id)
        if not job:
            raise NonRetryableProcessingError(f"Job {job_id} not found")
        step = session.get(ProcessingStep, step_id)
        if not step:
            raise NonRetryableProcessingError(f"Step {step_id} not found")

        stmt = select(ProductDocumentAssociation).where(ProductDocumentAssociation.document_id == document_id)
        assocs = session.exec(stmt).all()
        if not assocs:
            raise NonRetryableProcessingError(f"No products associated with document {document_id}")

        # ---- 2. Update stage status ----
        now = datetime.now(timezone.utc)
        step.status = StepStatus.processing
        step.started_at = now
        step.updated_at = now
        job.current_stage = ProcessingStage.enriching
        job.updated_at = now
        session.add(step)
        session.add(job)
        session.commit()

        provider = self._get_provider()
        attr_repo = AttributeRepository(session)

        for assoc in assocs:
            product = session.get(Product, assoc.product_id)
            if not product:
                continue

            # Check if valid enrichment already exists (e.g. from EnrichmentPipeline)
            existing_enrichment = session.exec(
                select(EnrichmentResult).where(
                    EnrichmentResult.product_id == product.id,
                    EnrichmentResult.status == EnrichmentStatus.completed,
                )
            ).first()

            if not existing_enrichment:
                attributes = attr_repo.list_by_product(product.id)
                verified_attrs_map = {
                    a.attribute_name: {
                        "raw_value": a.raw_value,
                        "normalized_value": a.normalized_value,
                        "unit": a.unit,
                        "confidence": a.confidence,
                    }
                    for a in attributes
                }

                product_context = {
                    "product_name": product.product_name,
                    "brand": product.brand,
                    "sku": product.sku,
                    "model": product.model,
                    "category": product.category,
                    "description": product.description,
                    "verified_attributes": verified_attrs_map,
                    "features": product.features or [],
                    "applications": product.applications or [],
                }

                try:
                    enrichment = provider.enrich(product_context)
                    claim_checker = ClaimChecker()
                    claim_res = claim_checker.check(
                        enrichment=enrichment,
                        verified_attributes=verified_attrs_map,
                        verified_features=product.features or [],
                        verified_applications=product.applications or [],
                    )
                    conf_calc = EnrichmentConfidenceCalculator()
                    enrich_conf = conf_calc.calculate(
                        claim_result=claim_res,
                        evidence_coverage=product.quality_score,
                        validation_health=85.0 if not claim_res.has_unsupported_claims else 40.0,
                        source_trust=0.9,
                        llm_confidence=enrichment.confidence,
                    )

                    old_enrichments = session.exec(
                        select(EnrichmentResult).where(EnrichmentResult.product_id == product.id)
                    ).all()
                    for old in old_enrichments:
                        session.delete(old)

                    enrich_result_db = EnrichmentResult(
                        product_id=product.id,
                        enrichment_type=EnrichmentType.description,
                        generated_value=json.dumps(enrichment.model_dump(), indent=2),
                        model=provider.model_name,
                        prompt_version=ENRICHMENT_PROMPT_VERSION,
                        confidence=enrich_conf,
                        status=EnrichmentStatus.completed,
                    )
                    session.add(enrich_result_db)

                    if enrichment.commerce_description:
                        product.commerce_description = enrichment.commerce_description
                    if claim_res.clean_features:
                        product.features = claim_res.clean_features
                    if claim_res.clean_applications:
                        product.applications = claim_res.clean_applications
                    if enrichment.keywords:
                        product.keywords = enrichment.keywords

                    product.updated_at = now
                    session.add(product)

                except Exception as enrich_err:
                    logger.error(f"Enrichment LLM call failed for product {product.id}: {enrich_err}")
                    old_enrichments = session.exec(
                        select(EnrichmentResult).where(EnrichmentResult.product_id == product.id)
                    ).all()
                    for old in old_enrichments:
                        session.delete(old)

                    failed_enrich_db = EnrichmentResult(
                        product_id=product.id,
                        enrichment_type=EnrichmentType.description,
                        generated_value="{}",
                        model=getattr(provider, "model_name", "unknown"),
                        prompt_version=ENRICHMENT_PROMPT_VERSION,
                        confidence=0.0,
                        status=EnrichmentStatus.failed,
                    )
                    session.add(failed_enrich_db)

                    step.status = StepStatus.failed
                    step.error_message = f"Enrichment LLM call failed: {enrich_err}"
                    step.updated_at = now
                    job.status = JobStatus.failed
                    job.error_message = f"Enrichment LLM call failed: {enrich_err}"
                    job.updated_at = now
                    session.add(step)
                    session.add(job)
                    session.commit()

                    err_str = str(enrich_err).lower()
                    if any(k in err_str for k in ["429", "503", "resource_exhausted", "retry in"]):
                        raise TransientProcessingError(f"Transient enrichment LLM failure: {enrich_err}") from enrich_err

                    raise NonRetryableProcessingError(f"Enrichment LLM call failed: {enrich_err}") from enrich_err

            # Safe search auto-indexing
            try:
                from app.services.indexing import IndexingService
                indexer = IndexingService(session)
                indexer.index_product(product.id)
            except Exception as idx_err:
                logger.warning(f"Search indexing failed for product {product.id}: {idx_err}")

        # ---- Complete step and job ----
        step.status = StepStatus.completed
        step.completed_at = now
        step.updated_at = now

        job.status = JobStatus.completed
        job.current_stage = ProcessingStage.completed
        job.completed_at = now
        job.updated_at = now

        session.add(step)
        session.add(job)
        session.commit()
        logger.info(f"EnrichmentStage completed for {len(assocs)} products from document {document_id}")


# ---------------------------------------------------------------------------
# DocumentProcessingService — orchestrates all stages
# ---------------------------------------------------------------------------

class DocumentProcessingService:
    def __init__(
        self,
        session: Session,
        parser: Optional[DocumentParser] = None,
        llm_provider=None,
    ):
        self.session = session
        self.parsing_stage = ParsingStage(parser)
        self.extraction_stage = ExtractionStage(llm_provider)
        self.validation_stage = ValidationStage()
        self.enrichment_stage = EnrichmentStage(llm_provider)

    def process_document(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        """
        Runs Stage 1: Parsing.
        """
        self.parsing_stage.execute(self.session, document_id, job_id, step_id)

    def extract_document(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        """
        Runs Stage 2: Extraction.
        """
        self.extraction_stage.execute(self.session, document_id, job_id, step_id)

    def validate_document(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        """
        Runs Stage 3: Validation.
        """
        self.validation_stage.execute(self.session, document_id, job_id, step_id)

    def enrich_document(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> None:
        """
        Runs Stage 4: Enrichment.
        """
        self.enrichment_stage.execute(self.session, document_id, job_id, step_id)

