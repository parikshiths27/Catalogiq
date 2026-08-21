# CatalogIQ

**CatalogIQ** is an enterprise-grade AI-powered product intelligence and catalog enrichment platform designed to ingest messy, multi-format industrial supplier catalogs, extract and normalize technical specifications, ground claims in verifiable manufacturer evidence, resolve cross-source conflicts, and export standardized, commerce-ready data in the official 252-column Unilog Delivery Format.

---

## Overview

Industrial and MRO catalogs frequently suffer from fragmented product data: inconsistent brand spellings, unstructured PDF spec sheets, missing attributes, conflicting manufacturer claims, non-standard units of measure, and unverified data. 

CatalogIQ transforms this unstructured data through an automated, evidence-backed pipeline. Every technical attribute extracted by CatalogIQ is grounded with verbatim source citations, normalized against authoritative registries, and checked against anti-hallucination guardrails before reaching downstream commerce channels.

---

## Key Capabilities

- **Multi-Format Document Ingestion**: Ingests and processes PDF, DOCX, XLSX, CSV, JSON, XML, TXT, MD, and HTML files into a unified Intermediate Representation (IR).
- **Batch & Archive Ingestion**: Supports multi-file batches and ZIP archives with individual file failure isolation, SHA-256 deduplication, and asynchronous Celery task tracking.
- **Automated Catalog Processing**: High-throughput tabular ingestion capable of processing 1,000+ items with end-to-end data pipeline orchestration.
- **Manufacturer & Brand Normalization**: Canonical resolution against master manufacturer registries with legal casing and registered trademark handling (`®`, `™`).
- **Taxonomy & Classpath Classification**: Multi-level hierarchical categorization mapped to approved industry taxonomies.
- **LOV-Constrained Technical Attributes**: Extraction and mapping to List of Values (LOV) with confidence scores (0.0 to 1.0).
- **Fraction & UOM Normalization**: Deterministic conversion of fractions (`.045` ↔ `3/64`), inch fractions, and SI unit standards (`kW` ↔ `W`, `in` ↔ `mm`, `gpm`, `dBA`).
- **Evidence Verification & Provenance**: Strict grounding tracking verbatim text quotes, page numbers, extraction methods, and source classifications.
- **Multi-Source Claim Reconciliation**: Automated comparison of competing claims across manufacturer spec sheets, distributor feeds, and reference masters with trust-weighted conflict detection.
- **Human Review & Quality Triage**: Interactive queue for resolving taxonomy classifications, low-confidence extractions, and multi-source conflicts with database-backed audit logging.
- **Explainable Quality Scoring**: 100-point dimensional score evaluating Identity, Taxonomy, Attributes, Evidence, Content, and Validation Gates.
- **CatalogIQ Assistant**: Grounded in-product help center powered by Google Gemini with live product context awareness and deterministic FAQ fast paths.
- **252-Column Delivery Export**: Full export conforming to the official 252-column Unilog delivery schema.

---

## Architecture

```
                                  [ Input Documents ]
                 (PDF, DOCX, XLSX, CSV, JSON, XML, TXT, MD, HTML, ZIP)
                                           │
                                           ▼
                                 [ Batch Ingestion ]
                      (SHA-256 Deduplication, Size Validation)
                                           │
                                           ▼
                            [ Celery Asynchronous Workers ]
                             (Redis Task Queue Orchestration)
                                           │
                                           ▼
                             [ Parsing & Common IR Engine ]
                     (Docling Parser, Tabular Parser, Text Parser)
                                           │
                                           ▼
                           [ Semantic & Tabular Extraction ]
                       (Deterministic Rules + LLM Extraction)
                                           │
                                           ▼
                           [ Normalization & UOM Standards ]
                     (Canonical Units, Decimal/Fraction Lookup)
                                           │
                                           ▼
                          [ Evidence Provenance & Citations ]
                      (Source Bounding Text, Page Citations)
                                           │
                                           ▼
                       [ Multi-Source Claims Reconciliation ]
                       (Trust Hierarchy, Conflict Resolution)
                                           │
                                           ▼
                            [ AI Commerce Content Builder ]
                     (Invoice, Mobile, Short & Long Descriptions)
                                           │
                                           ▼
                       [ Validation Engine & Quality Scoring ]
                     (LOV Compliance, Gate Checks, 0-100 Score)
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
                [ Product Status ]                    [ Product Status ]
                    VERIFIED                            NEEDS_REVIEW
                        │                                     │
                        │                                     ▼
                        │                            [ Human Review Queue ]
                        │                             (Taxonomy Override,
                        │                              Audit Log History)
                        │                                     │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼
                       [ Dual Indexing & Search Engine ]
                   (PostgreSQL Lexical + Qdrant Vector Store)
                                           │
                                           ▼
                       [ 252-Column Delivery Export & API ]
                      (CSV Export, REST APIs, React Frontend)
```

### Core Technologies
- **Backend**: FastAPI (Python 3.11), SQLModel / SQLAlchemy, Pydantic v2
- **Task Queue**: Celery with Redis broker
- **Database**: PostgreSQL
- **Vector Search**: Qdrant Vector Database
- **LLM Engine**: Google Gemini (`gemini-3.5-flash`) / Ollama (`qwen3:8b`)
- **Frontend**: React 18, TypeScript, Vite, TailwindCSS, Lucide Icons

---

## Repository Structure

```
Catalogiq/
├── backend/
│   ├── alembic/                  # Database migration scripts
│   ├── app/
│   │   ├── api/v1/               # FastAPI endpoints (documents, products, reviews, assistant, jobs)
│   │   ├── core/                 # App configuration and constants
│   │   ├── db/                   # Database session and engine setup
│   │   ├── models/               # SQLModel entities (Product, Attribute, Validation, Document, Batch)
│   │   ├── repositories/         # Database access layer
│   │   ├── services/             # Core business logic (pipeline, parser, reconciler, assistant)
│   │   │   ├── embeddings/       # Vector embedding providers
│   │   │   ├── enrichment/       # Taxonomy, brand normalizer, description builder
│   │   │   └── llm/              # Gemini and Ollama LLM provider integrations
│   │   └── workers/              # Celery tasks and worker orchestration
│   ├── scripts/                  # Data ingestion and utility scripts
│   ├── tests/                    # Pytest acceptance and unit test suites
│   ├── alembic.ini
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   ├── public/                   # Static web assets
│   ├── src/
│   │   ├── components/           # Reusable UI components & Assistant widget
│   │   ├── features/             # Feature views (Upload, Products, Reviews, Jobs, Health, Search)
│   │   ├── hooks/                # React custom hooks
│   │   ├── lib/                  # Utility functions
│   │   ├── App.tsx               # Root component and router
│   │   └── main.tsx              # Application entry point
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── docs/                         # Technical architecture and domain documentation
├── docker-compose.yml            # Multi-container orchestration (DB, Redis, Qdrant)
├── .env.example                  # Environment configuration template
├── .gitignore
├── PROJECT_SPEC.md               # Technical specification document
└── README.md
```

---

## Supported Formats

CatalogIQ handles diverse document inputs across industrial supply chains:

| Format | Extension | Parser Implementation | Intermediate Representation (IR) |
|---|---|---|---|
| PDF Documents | `.pdf` | Multi-format PDF layout parser | Pages, bounding boxes, tables, text spans |
| Microsoft Word | `.docx` | Document structure parser | Structured headings, paragraphs, tables |
| Microsoft Excel | `.xlsx` | Tabular spreadsheet parser | Multi-sheet rows, columns, headers |
| CSV Catalogs | `.csv` | Tabular delimiter parser | Delimited records with header inference |
| Plain Text | `.txt` | Paginated text parser | Structured text blocks |
| Markdown | `.md` | Markdown AST parser | Sections, headings, tables |
| JSON Files | `.json` | Key-value hierarchy parser | Entity objects and attribute maps |
| XML Files | `.xml` | XML DOM entity parser | Node trees and attribute elements |
| HTML / HTM | `.html`, `.htm` | HTML DOM parser | Cleaned tables, stripped scripts/styles |
| ZIP Archives | `.zip` | Secure archive unpacker | Decompressed batch items |

---

## Enrichment Pipeline

The automated enrichment pipeline runs across seven sequential phases:

1. **Ingestion & Validation**: Checks file magic bytes, computes SHA-256 content hashes, deduplicates identical documents, and registers batch items.
2. **Parsing & Common IR**: Converts heterogeneous formats into a unified Intermediate Representation.
3. **Identity Normalization**: Matches brand names and manufacturer aliases against the master registry (e.g. `"milw"` → `"Milwaukee Electric Tool Corporation"`, `"Milwaukee®"`).
4. **Taxonomy & Attribute Extraction**: Classifies products into approved multi-level taxonomies and extracts technical specifications with LOV mapping and confidence scoring.
5. **Normalizing & Engineering Units**: Standardizes numeric values, decimal fractions, and units into standard SI formats.
6. **AI Commerce Content Generation**:
   - **Invoice Description**: Strict uppercase abbreviation (<= 40 chars), e.g. `CUT OFF DISC 5IN .045IN 7/8IN MTL`.
   - **Mobile Description**: Comma-separated structured summary (60–80 chars), e.g. `Milwaukee, 5 in x .045 in x 7/8 in Cut-Off Disc, 49-94-0013`.
   - **Short Description / Title**: Structured product title with registered trademarks.
   - **Long Description**: Anti-hallucination verified summary with technical specifications.
7. **Validation Gates & Dual Search Indexing**: Calculates the 100-point Quality Score, routes products with issues to `needs_review`, and generates vector embeddings in Qdrant and lexical records in PostgreSQL.

---

## Human Review & Quality Triage

Products with potential data issues are automatically flagged for manual review:

- **Review Categories**:
  - `taxonomy_unresolved`: Extracted category does not match an approved classpath.
  - `low_confidence`: Attribute extraction confidence is below the 75% threshold.
  - `missing_required_attribute`: Mandatory category specification is missing.
  - `cross_source_conflict`: Contradictory values detected across data sources.
  - `range_violation`: Value falls outside expected engineering limits.
- **Workflow**:
  - Reviewers can choose from searchable approved taxonomy classpaths or supply verified custom overrides.
  - The system prevents accepting invalid or unapproved values.
  - Every resolution generates an `AuditLog` entry, recalculates the product's Quality Score, and automatically updates the product status to `verified` when all issues are resolved.

---

## Evidence & Provenance

Every attribute in CatalogIQ is backed by explicit source classification and verifiable citations:

- `RAW_INPUT`: Value directly supplied in the raw uploaded catalog row.
- `REFERENCE_MASTER`: Value from an authoritative manufacturer registry or master taxonomy.
- `MANUFACTURER_SOURCE`: Value extracted from official OEM technical datasheets and spec sheets.
- `DERIVED`: Value calculated via deterministic unit conversion or fraction lookup.
- `MODEL_EXTRACTION`: Value extracted by LLM semantic reasoning from source text.
- `MODEL_INFERENCE`: Categorical classification inferred by AI models.

---

## Multi-Source Reconciliation

When multiple catalogs or datasheets provide conflicting specifications for the same product, CatalogIQ's **MultiSourceReconciler** evaluates claims across four status levels:

- `AGREEMENT`: All sources provide identical values.
- `EQUIVALENT`: Values differ in unit or text format (e.g. `11 kW` vs `11000 W`, `0.5 in` vs `1/2 in`) but resolve to identical SI base representations.
- `MISSING`: An attribute appears in one source but is omitted in another without contradiction.
- `CONFLICTING`: Sources provide incompatible values (e.g. `11 kW` vs `7.5 kW`), generating a flagged issue for human resolution with source trust weighting.

---

## CatalogIQ Assistant

The in-product Assistant provides interactive help and data triage powered by Google Gemini:

- **Architecture Knowledge**: Explains ingestion formats, batch processing, enrichment formulas, and search mechanisms.
- **Product Context Grounding**: When asking about a specific product (e.g. `49-94-0013`), the Assistant queries the live database to retrieve exact attributes, validation issues, and source citations.
- **Deterministic FAQ Fast-Path**: Common architectural and workflow questions resolve with sub-millisecond latency.
- **Zero-Leak Security**: System prompts strictly protect internal API keys, database credentials, and security configurations.

---

## 252-Column Delivery Export

CatalogIQ provides native export conforming to the official 252-column Unilog Delivery Schema:

- Includes core product attributes (`Mfg_Part_Num`, `BRAND_NAME`, `CATEGORY`, `SUBCATEGORY`).
- Populates commerce descriptions (`INVOICE_DESC`, `MOBILE_DESC`, `SHORT_DESC`, `LONG_DESC1`, `RETAIL_DESC`).
- Maps packaging and commercial units (`Selling Qty`, `Selling UOM`, `Pricing UOM`).
- Expands category-specific technical attributes into dedicated delivery columns.

---

## Setup & Local Installation

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Docker & Docker Compose
- Google Gemini API Key (for LLM enrichment and Assistant)

### 1. Clone the Repository
```bash
git clone https://github.com/parikshiths27/Catalogiq.git
cd Catalogiq
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

### 3. Start Infrastructure Services (Docker)
```bash
docker-compose up -d
```
*Starts PostgreSQL (`5432`), Redis (`6379`), and Qdrant (`6333`).*

### 4. Backend Setup
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1   # On Windows (or source venv/bin/activate on Unix)
pip install -r requirements.txt
alembic upgrade head
```

### 5. Start Backend Services
**Start FastAPI Server (Terminal 1):**
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Start Celery Worker (Terminal 2):**
```bash
celery -A app.workers.celery_app worker -l info -P solo
```

### 6. Frontend Setup
```bash
cd ../frontend
npm install
npm run dev
```
*Frontend runs at `http://localhost:5173`.*

---

## Testing

Run the automated backend test suites:
```bash
cd backend
python -m pytest tests/test_assistant.py tests/test_full_pipeline_acceptance.py tests/test_hackathon_enrichment.py tests/test_reviews_api.py -v
```

Validate frontend TypeScript compilation and production bundle:
```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## Production & Deployment Notes

- **Separation of Concerns**: The frontend Vite SPA can be deployed independently to Vercel, Netlify, or Cloudflare Pages with an API proxy pointing to the FastAPI backend.
- **Backend Scalability**: FastAPI runs as an ASGI application behind Nginx/Caddy, with Celery workers scaled horizontally to process document batches.
- **Database & Cache**: Requires managed PostgreSQL (with pgvector if applicable), Redis, and Qdrant instances in production.
- **Security**: Never commit `.env` or API credentials. Secrets should be injected via cloud environment variables or secret managers.

---

## Project Status

CatalogIQ is actively maintained and tested against full acceptance suites covering multi-format ingestion, 1,000-row batch catalogs, AI commerce enrichment, human review triage, multi-source reconciliation, and 252-column export generation.
