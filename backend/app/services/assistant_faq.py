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
            "CatalogIQ is an AI-powered product intelligence and catalog enrichment platform. "
            "It ingests multi-format technical catalogs and spec sheets (PDF, DOCX, XLSX, CSV, TXT, JSON, XML, HTML, MD), "
            "extracts structured technical attributes with evidence traceability, validates data quality and unit standards, "
            "reconciles multi-source data conflicts, enriches product commerce descriptions and taxonomies, and provides "
            "high-precision hybrid search and faceted filtering."
        ),
        "suggestions": [
            "What file formats are supported?",
            "How do I upload a catalog?",
            "How does search work?",
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
            "You can upload single files, multi-file batches, folder selections, or ZIP archives via the Upload Page (`/upload`). "
            "CatalogIQ supports PDF, DOCX, XLSX, CSV, TXT, JSON, XML, HTML, and Markdown files up to 50MB. "
            "Upon upload, documents are queued for asynchronous background processing through parsing, extraction, validation, "
            "enrichment, and search indexing."
        ),
        "suggestions": [
            "What file formats are supported?",
            "How does batch processing work?",
            "What happens during document processing?",
        ],
    },
    {
        "id": "supported_formats",
        "patterns": [
            "what file formats does catalogiq support",
            "what file formats does catalogiq support?",
            "what file formats are supported",
            "what file formats are supported for ingestion",
            "what formats are supported",
            "supported file formats",
            "supported formats",
            "supported file types",
            "what file types can i upload",
            "file formats",
        ],
        "message": (
            "CatalogIQ supports multi-format document ingestion across:\n"
            "- **PDF** (`.pdf`): Parsed via DoclingParser / PDF layout engine\n"
            "- **Word** (`.docx`): Document parsing via Docling / Word parser\n"
            "- **Excel** (`.xlsx`): Tabular worksheet parsing via ExcelParser\n"
            "- **CSV** (`.csv`): Tabular product records via CSVParser\n"
            "- **Plain Text** (`.txt`) & **Markdown** (`.md`): Paged document extraction via TextParser\n"
            "- **JSON** (`.json`): Structured key-value attribute tables via JSONParser\n"
            "- **XML** (`.xml`): Entity node parsing via XMLParser\n"
            "- **HTML / HTM** (`.html`, `.htm`): Web catalog and spec tables via HTMLParser\n"
            "In addition, you can upload **ZIP archives** containing any of these supported formats. "
            "All formats are converted into a unified Intermediate Representation (IR) before downstream extraction."
        ),
        "suggestions": [
            "What happens when I upload Excel?",
            "Can I upload a ZIP?",
            "How does batch processing work?",
        ],
    },
    {
        "id": "pdf_only_inquiry",
        "patterns": [
            "does catalogiq only support pdfs",
            "does catalogiq only support pdf",
            "is catalogiq pdf only",
            "is catalogiq only for pdfs",
            "pdf only",
            "only pdfs",
            "do you only support pdf",
            "does it only support pdf",
        ],
        "message": (
            "No, CatalogIQ is not PDF-only. While it offers advanced layout parsing for technical PDFs, "
            "it natively supports multiple document formats including PDF, DOCX, XLSX (Excel), CSV, TXT, "
            "MD (Markdown), JSON, XML, and HTML/HTM, as well as multi-file batches and ZIP archives."
        ),
        "suggestions": [
            "What file formats does CatalogIQ support?",
            "What happens when I upload Excel?",
            "Can I upload multiple files?",
        ],
    },
    {
        "id": "excel_upload_flow",
        "patterns": [
            "what happens when i upload excel",
            "what happens when i upload excel?",
            "what happens when i upload an excel file",
            "if i upload an excel file what happens",
            "what happens if i upload an excel file",
            "if i upload an excel file, what happens",
            "if i upload a excel, what happens",
            "if i upload an excel, what happens",
            "what happens after an excel upload",
            "can i upload excel",
            "can i upload an excel file",
            "excel file upload",
            "upload excel",
            "excel upload",
            "xlsx support",
        ],
        "message": (
            "When you upload an Excel (`.xlsx`) file in CatalogIQ:\n"
            "1. **Ingestion & Validation**: File format, file size, and SHA-256 checksum are validated.\n"
            "2. **Excel Parsing**: The `ExcelParser` extracts worksheet rows and tables into the common Intermediate Representation (IR).\n"
            "3. **Attribute Extraction**: Product identifiers and technical specifications are extracted from the structured sheets.\n"
            "4. **Validation & Quality Scoring**: Attributes are normalized to standard SI units, checked against category rules, and assigned a quality score.\n"
            "5. **Commerce Enrichment**: The product receives canonical manufacturer/brand normalization, taxonomy classification, and AI commerce descriptions.\n"
            "6. **Search Indexing**: Embeddings and metadata are indexed in Qdrant (vector) and PostgreSQL (keyword) for hybrid search."
        ),
        "suggestions": [
            "What file formats does CatalogIQ support?",
            "How does batch processing work?",
            "What does needs_review mean?",
        ],
    },
    {
        "id": "multi_file_upload",
        "patterns": [
            "can i upload multiple files",
            "multi file upload",
            "upload multiple files",
            "how to upload multiple files",
            "can i upload more than one file",
            "multiple files",
        ],
        "message": (
            "Yes! CatalogIQ supports Level 3 Batch Ingestion. You can upload multiple files simultaneously or select entire folders on the Upload page. "
            "The system creates an `IngestionBatch` with individual `IngestionBatchItem` records, allowing each document to be processed independently "
            "by Celery workers while displaying live aggregated batch progress."
        ),
        "suggestions": [
            "How does batch processing work?",
            "Can I upload a ZIP?",
            "What happens if the same file is uploaded twice?",
        ],
    },
    {
        "id": "zip_upload_flow",
        "patterns": [
            "can i upload a zip",
            "can i upload zip",
            "zip upload",
            "zip file upload",
            "upload zip archive",
            "zip ingestion",
            "uploading zip",
        ],
        "message": (
            "Yes, you can upload ZIP archives. CatalogIQ inspects the archive with strict security checks (verifying uncompressed size limits, "
            "file count ceilings, and preventing directory traversal), extracts all supported document files (`.pdf`, `.xlsx`, `.csv`, `.docx`, `.txt`, etc.), "
            "and creates a batch where each valid file is processed independently."
        ),
        "suggestions": [
            "How does batch processing work?",
            "What file formats are supported?",
            "What happens if the same file is uploaded twice?",
        ],
    },
    {
        "id": "batch_processing_workflow",
        "patterns": [
            "how does batch processing work",
            "batch processing",
            "how batch works",
            "batch ingestion",
            "how does batch ingestion work",
            "level 3 batch ingestion",
        ],
        "message": (
            "CatalogIQ Level 3 Batch Ingestion operates in sequential stages:\n"
            "1. **Batch Creation**: An `IngestionBatch` is created with an `IngestionBatchItem` for every file in the batch.\n"
            "2. **Independent Processing**: Each valid file creates a distinct `Document` record and `ProcessingJob` executed asynchronously by Celery workers.\n"
            "3. **Partial Failure Isolation**: If a single file is corrupted or unsupported, its item is marked failed while valid files in the batch continue processing normally.\n"
            "4. **Aggregated Progress Tracking**: Batch endpoints track total, pending, processing, completed, and failed counts with real-time percentage progress.\n"
            "5. **Content Deduplication**: Previously processed files (matching SHA-256 hashes) are recognized (`cached=True`) without dispatching duplicate Celery tasks."
        ),
        "suggestions": [
            "What happens if the same file is uploaded twice?",
            "Can I upload a ZIP?",
            "What does needs_review mean?",
        ],
    },
    {
        "id": "document_processing_stages",
        "patterns": [
            "explain processing stages",
            "what are the processing stages",
            "processing stages",
            "document processing stages",
            "what happens during document processing",
            "how does document processing work",
            "processing steps",
        ],
        "message": (
            "When a document is uploaded, CatalogIQ processes it through 5 sequential pipeline stages:\n"
            "1. **Format Validation & Ingestion**: File type, size, and SHA-256 hash are checked.\n"
            "2. **Document Parsing**: Specialized parsers convert the file into unified Intermediate Representation (IR).\n"
            "3. **Technical Attribute Extraction**: Product identifiers and technical specifications are extracted with source quotes.\n"
            "4. **Validation & Quality Scoring**: LOV validation, unit normalization (SI units), and data completeness checks are applied.\n"
            "5. **Commerce Enrichment & Indexing**: Canonical brand/manufacturer resolution, taxonomy classification, descriptions generation, and vector/keyword search indexing."
        ),
        "suggestions": [
            "What file formats does CatalogIQ support?",
            "How does batch processing work?",
            "What is quality score?",
        ],
    },
    {
        "id": "duplicate_upload_handling",
        "patterns": [
            "what happens if the same file is uploaded twice",
            "what happens if a duplicate file is uploaded",
            "duplicate file upload",
            "reuploading same file",
            "uploading same file twice",
            "duplicate upload",
            "duplicate handling",
        ],
        "message": (
            "When a file with an identical SHA-256 hash is uploaded again:\n"
            "1. CatalogIQ detects the matching hash in the document registry.\n"
            "2. In batch uploads, a new `IngestionBatchItem` is created linked to the existing `Document` and marked `cached=True`.\n"
            "3. Redundant Celery processing jobs are avoided, preventing duplicate background workloads while preserving batch tracking integrity."
        ),
        "suggestions": [
            "How does batch processing work?",
            "What file formats are supported?",
            "What does needs_review mean?",
        ],
    },
    {
        "id": "enrichment_overview",
        "patterns": [
            "how is a product enriched",
            "how is a product enriched?",
            "how a product is enriched",
            "what is product enrichment",
            "how does enrichment work",
            "product enrichment",
            "what does enrichment do",
            "ai commerce enrichment",
            "how does product enrichment work",
        ],
        "message": (
            "CatalogIQ Product Content Enrichment enhances raw extracted technical attributes into structured catalog data:\n"
            "- **Canonical Normalization**: Standardizes brand and manufacturer names against enterprise registries.\n"
            "- **Taxonomy & Classpath**: Classifies products into standard hierarchical categories.\n"
            "- **Attribute LOV & UOM Standardization**: Standardizes units to SI norms (e.g. converting fractions and imperial units) and enforces List of Values (LOV) rules.\n"
            "- **Commerce Content Generation**: Generates executive commerce summaries, short marketing blurbs, bulleted feature highlights, and target applications strictly grounded in verified specs.\n"
            "- **Provenance & Confidence**: Maintains evidence links back to source documents and routes low-confidence or conflicting items to Human Review (`/reviews`)."
        ),
        "suggestions": [
            "What does needs_review mean?",
            "What is quality score?",
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
            "why does a product need human review",
            "why does a product need human review?",
            "why does a product need review",
            "why a product needs human review",
            "what does needs review mean",
            "what does needs_review mean",
            "why is my product marked needs review",
            "needs review status",
            "needs review",
            "needs_review",
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
            "What search modes are available?",
            "How does hybrid search work?",
            "What does search degraded mode mean?",
        ],
    },
    {
        "id": "multi_source_reconciliation",
        "patterns": [
            "what is multi-source reconciliation",
            "what is multi source reconciliation",
            "how does multi-source reconciliation work",
            "how does multi source reconciliation work",
            "multi-source reconciliation",
            "multi source reconciliation",
            "reconciliation",
        ],
        "message": (
            "Multi-Source Reconciliation resolves discrepancies when product information is provided by multiple sources:\n"
            "1. **Source Hierarchy & Trust Levels**: CatalogIQ distinguishes `MANUFACTURER_SOURCE` (highest authority), `REFERENCE_MASTER` (e.g. brand/taxonomy dictionaries), and `RAW_INPUT` (customer feeds/distributor files).\n"
            "2. **Conflict Detection**: Competing claims for attributes (e.g. voltage, dimensions, materials) are compared.\n"
            "3. **Consensus Resolution**: If sources agree or higher authority confirms a normalized value, the winner is automatically selected with full provenance recorded.\n"
            "4. **Human Escalation**: Irreconcilable differences are routed to Human Review (`/reviews`) where reviewers can select winning claims or input verified values."
        ),
        "suggestions": [
            "Where does a product attribute come from?",
            "Why does a product need human review?",
            "What does needs_review mean?",
        ],
    },
    {
        "id": "attribute_provenance",
        "patterns": [
            "where does a product attribute come from",
            "where do product attributes come from",
            "where does an attribute come from",
            "how are attributes extracted",
            "attribute extraction",
            "attribute evidence",
        ],
        "message": (
            "Product attributes in CatalogIQ originate with strict provenance tracking:\n"
            "1. **Extraction**: Attributes are parsed from technical documents (PDF spec sheets, Excel matrices, Word manuals, CSV tables) using layout-aware parsers and LLM extraction.\n"
            "2. **Evidence Grounding**: Every extracted attribute stores verbatim source text citations, document page numbers, and bounding-box coordinates in the `attributeevidence` table.\n"
            "3. **Normalization**: Raw text is parsed into numeric values and standardized SI units according to enterprise LOV (List of Values) dictionaries.\n"
            "4. **Verification**: Attributes are verified against manufacturer master records or cross-checked against independent document sources."
        ),
        "suggestions": [
            "What is Multi-Source Reconciliation?",
            "What does verified mean?",
            "What does needs_review mean?",
        ],
    },
    {
        "id": "verified_status",
        "patterns": [
            "what does verified mean",
            "what is verified",
            "verified status",
            "what does verified status mean",
            "how does a product become verified",
        ],
        "message": (
            "A product status of `verified` indicates that the item has satisfied all quality, validation, and provenance gates:\n"
            "1. **Identity & Taxonomy**: Canonical Brand, Manufacturer, MPN/SKU, and Taxonomy Classpath are fully resolved.\n"
            "2. **Quality Score**: Achieved high quality score (>=70%) with complete required attributes.\n"
            "3. **Zero Open Errors**: No unresolved unit inconsistencies, LOV violations, or critical validation issues.\n"
            "4. **Export Readiness**: The product is fully structured and validated for 252-column client catalog delivery."
        ),
        "suggestions": [
            "What does needs_review mean?",
            "What is quality score?",
            "How does the 252-column export work?",
        ],
    },
    {
        "id": "export_252_columns",
        "patterns": [
            "how does the 252-column export work",
            "how does the 252 column export work",
            "how does 252-column export work",
            "how does 252 column export work",
            "252-column export",
            "252 column export",
            "export format",
            "unilog export format",
        ],
        "message": (
            "The 252-column export generates the authoritative Unilog Client Delivery Format in CSV or Excel (XLSX):\n"
            "1. **Standard Header Schema**: Exactly 252 standardized columns in canonical delivery sequence.\n"
            "2. **Identity & Taxonomy**: Populates `Dept`, `Class`, `Fine`, `Classpath`, `MANUFACTURER_NAME`, `BRAND_NAME`, `Mfg_Part_Num`, `SKU - MY_PART_NUMBER`.\n"
            "3. **Dynamic Attributes Slots**: Maps up to 50 extracted technical attributes into `ATTRIBUTE_LABEL 1..50`, `ATTRIBUTE_VALUE 1..50`, and `ATTRIBUTE_UOM 1..50`.\n"
            "4. **Commerce Content**: Includes `MOBILE_DESC` (<=80 chars), `INVOICE_DESC` (<=40 chars uppercase), `SHORT_DESC`, `LONG_DESC1`, and `ITEM_FEATURES_1..20`.\n"
            "5. **Asset Links**: Synthesizes standardized image and spec sheet filenames (e.g. `Brand_SKU_Specification_Sheet.pdf`)."
        ),
        "suggestions": [
            "What does verified mean?",
            "How is a product enriched?",
            "What file formats does CatalogIQ support?",
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
