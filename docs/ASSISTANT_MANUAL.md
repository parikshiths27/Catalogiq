# CATALOGIQ ASSISTANT USER MANUAL & SYSTEM KNOWLEDGE

This document is the authoritative, grounded user manual for CatalogIQ — an AI-powered Product Intelligence and Catalog Enrichment Platform.

---

## 1. What is CatalogIQ?
CatalogIQ is an enterprise product intelligence platform designed to ingest raw, unstructured technical product catalogs (PDFs, spec sheets, data sheets), extract structured engineering attributes with evidence traceability, validate data completeness and quality, reconcile multi-source data conflicts, generate AI commerce descriptions, and provide high-precision hybrid search and faceted filtering.

---

## 2. Uploading Documents
- Users upload technical PDFs or product catalog documents via the **Upload Page** (`/upload`).
- Ingestion accepts PDF files up to 50MB.
- Upon upload, a unique `document_id` and an initial background `ProcessingJob` are created with `queued` status.

---

## 3. Document Processing
Processing occurs asynchronously in sequential stages:
1. **Ingestion & Validation**: File type, size, and checksum verification.
2. **Parsing**: Layout analysis and structural extraction into Intermediate Representation (IR).
3. **Extraction**: LLM and deterministic extraction of product metadata and technical attributes.
4. **Validation & Quality Scoring**: Completeness, unit normalization, confidence scoring, and issue detection.
5. **Enrichment**: Generation of commerce descriptions, feature bullet points, and SEO content.
6. **Indexing**: Vector embedding creation and Qdrant + PostgreSQL payload synchronization.

---

## 4. Parsing (Docling IR)
- CatalogIQ uses Docling parser (or fallback parser) to convert raw PDFs into a structured Intermediate Representation (IR).
- IR contains structured tables, page text blocks, section headers, and bounding metadata.
- Preserves exact page numbers and original text snippets for evidence traceability.

---

## 5. Extraction
- Combines deterministic table parsing with LLM structured extraction (using Google Gemini).
- Extracts candidate core identity (`product_name`, `sku`, `model`, `brand`, `category`, `subcategory`) and technical attributes (`voltage`, `power`, `speed`, `ip_rating`, `weight`, etc.).
- Constrained by grounding rules to prevent hallucinated values.

---

## 6. Product Attributes
- Every product attribute includes:
  - `attribute_name`: Canonical snake_case identifier (e.g., `rated_power`).
  - `display_name`: Human-readable label (e.g., `Rated Power`).
  - `raw_value`: Original extracted value string (e.g., `5.5 kW`).
  - `normalized_value`: Standardized value (e.g., `5.5`).
  - `unit`: Standard SI unit (e.g., `kW`).
  - `confidence`: Confidence score between `0.0` and `1.0`.
  - `status`: Attribute state (`unverified`, `verified`, `conflict`, `rejected`).

---

## 7. Evidence and Provenance
- Every extracted attribute links to `AttributeEvidence`:
  - `evidence_text`: Verbatim text quote from source PDF.
  - `page_number`: 1-indexed page number where evidence was located.
  - `extraction_method`: `deterministic`, `llm`, or `llm_inference`.
  - `evidence_verified`: Boolean verifying verbatim match against document IR.

---

## 8. Confidence
- Attribute confidence combines:
  - Extraction method weight (deterministic = high, direct LLM = medium-high, inference = lower).
  - Evidence verification status.
  - Unit normalization validity.
  - Rule-based validation results.
- Attributes with confidence $< 0.70$ generate Human Review flags.

---

## 9. Validation
- Rule-based validation engine checks:
  - Required category attributes (e.g., Electric Motors require `voltage` and `power`).
  - Unit equivalence and range sanity checks.
  - Mojibake character repair.
  - Completeness calculator computes percentage of populated required attributes.

---

## 10. Multi-Source Reconciliation
- When multiple documents describe the same product (matching SKU or Model + Brand):
  - CatalogIQ detects candidate entities without automatic aggressive merging.
  - Level 1: Exact SKU & Brand match.
  - Level 2: Exact Model & Brand match.
  - Level 3: High semantic similarity candidate.
- Reconciles conflicting attribute values across sources using source trust levels, evidence verification, and SI unit conversions.
- Unresolved conflicts generate Human Review tasks in `/reviews`.

---

## 11. Enrichment
- AI Commerce Enrichment stage generates:
  - `commerce_description`: Executive commerce summary.
  - `short_description`: Concise marketing blurbs.
  - `features`: Key bulleted product capabilities.
  - `applications`: Typical industrial use-cases.
- Enrichment operates strictly on verified attribute context — zero invented specifications.

---

## 12. Quality Score
- Product `quality_score` (0.0% to 100.0%) measures overall catalog health:
  - **Completeness Rate** (40% weight): Percentage of expected category attributes populated.
  - **Verification Rate** (30% weight): Percentage of attributes with verified evidence.
  - **Confidence Coverage** (20% weight): Average confidence across attributes.
  - **Review Hygiene** (10% weight): Absence of unflagged conflicts or errors.

---

## 13. Product Statuses
- **`draft`**: Newly extracted product awaiting initial validation/review.
- **`needs_review`**: Product contains low-confidence attributes, missing required fields, or cross-source conflicts.
- **`verified`**: Product fully validated, passed quality thresholds, and approved for catalog export/search.

---

## 14. Search
- CatalogIQ search provides three operational search modes: `hybrid` (default), `semantic`, and `keyword`.
- Endpoints: `GET /api/v1/search` and `GET /api/v1/search/facets`.

---

## 15. Keyword Search
- Lexical search powered by PostgreSQL `ILIKE` pattern matching across SKU, Model, Name, Brand, Category, and Attributes.
- Multi-field scoring hierarchy: Exact SKU (1.00) > Exact Model (0.95) > Exact Name (0.90) > Exact Brand (0.85) > Substrings (0.80–0.60) > Attribute match (0.55).

---

## 16. Semantic Search
- Vector search powered by Qdrant vector database and FastEmbed embedding provider (`BAAI/bge-small-en-v1.5`, 384 dimensions).
- Captures conceptual and natural language intent (e.g. "motor for high temperature continuous pump").

---

## 17. Hybrid Search
- Combines PostgreSQL lexical candidates and Qdrant vector candidates.
- Intent-weighted score fusion with query intent detection:
  - `IDENTIFIER` (0.80 kw / 0.20 sem)
  - `NATURAL_LANGUAGE` (0.30 kw / 0.70 sem)
  - `MIXED` (0.50 kw / 0.50 sem)
- Clamped exact match priority boost.

---

## 18. Filters and Facets
- Multi-select filtering by `category`, `brand`, `status`, `subcategory`, `min_quality_score`, `max_quality_score`.
- Disjunctive faceting (calculates facet counts for unselected options within category/brand without restricting counts to current selection).
- Dynamic technical attribute facet generation.

---

## 19. Ranking
- 4-tier deterministic sorting order:
  1. `ranking_priority DESC` (`EXACT_SKU` = 3, `EXACT_MODEL` = 2, `EXACT_NAME` = 1, `NONE` = 0)
  2. `hybrid_score DESC`
  3. `quality_score DESC`
  4. `product_id ASC` (Deterministic tie-break)
- Guarantees exact SKU match always outranks non-exact semantic candidates.

---

## 20. Processing Failures
- Common processing errors:
  - `CorruptedPDFError`: Unreadable PDF structure.
  - `ExtractionError`: LLM provider rate limit or structural failure (retried automatically up to 3 times).
  - `LowQualityError`: Quality score below minimum threshold.
- Failed steps display detailed error logs in Jobs view (`/jobs`).

---

## 21. Search Degraded Modes
- If an engine component fails, CatalogIQ degrades gracefully without failing:
  - `vector_unavailable`: Qdrant offline; falls back to PostgreSQL keyword search.
  - `embedding_failed`: Embedding provider error; falls back to keyword search.
  - `keyword_unavailable`: Database issue; falls back to vector search.
- Degraded mode is clearly indicated by an amber badge in the Search UI.

---

## 22. Common User Questions
- **Why is my product marked Needs Review?**: Low confidence attributes (<70%), missing required specs for category, or cross-source reconciliation conflicts.
- **How do I fix a conflict?**: Go to Human Review (`/reviews`), select the product, and accept source A, accept source B, or enter a custom verified value.
- **Why did search return Degraded mode?**: One search subsystem (vector or DB) was temporarily unavailable; results fall back to the operational engine seamlessly.
