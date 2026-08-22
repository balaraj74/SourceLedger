```text
   ███████╗ ██████╗ ██╗   ██╗██████╗  ██████╗███████╗██╗     ███████╗██████╗  ██████╗ ███████╗██████╗ 
   ██╔════╝██╔═══██╗██║   ██║██╔══██╗██╔════╝██╔════╝██║     ██╔════╝██╔══██╗██╔════╝ ██╔════╝██╔══██╗
   ███████╗██║   ██║██║   ██║██████╔╝██║     █████╗  ██║     █████╗  ██║  ██║██║  ███╗█████╗  ██████╔╝
   ╚════██║██║   ██║██║   ██║██╔══██╗██║     ██╔══╝  ██║     ██╔══╝  ██║  ██║██║   ██║██╔══╝  ██╔══██╗
   ███████║╚██████╔╝╚██████╔╝██║  ██║╚██████╗███████╗███████╗███████╗██████╔╝╚██████╔╝███████╗██║  ██║
   ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚══════╝╚══════╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝
```

**SourceLedger** is an AI-powered Product Intelligence Engine designed to convert unstructured, messy industrial product datasheets, catalog PDFs, web pages, and CSV listings into normalized, commerce-ready product records with complete explainability, confidence scoring, and field-level source provenance.

---

## Table of Contents

1. [What is SourceLedger?](#1-what-is-sourceledger)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [Key Features](#4-key-features)
5. [How SourceLedger Works](#5-how-sourceledger-works)
6. [Multi-Agent Architecture](#6-multi-agent-architecture)
7. [System Architecture](#7-system-architecture)
8. [Project Structure](#8-project-structure)
9. [Technology Stack](#9-technology-stack)
10. [API Reference](#10-api-reference)
11. [Database](#11-database)
12. [Authentication & Security](#12-authentication--security)
13. [Prerequisites](#13-prerequisites)
14. [Quick Start](#14-quick-start)
15. [Manual Installation](#15-manual-installation)
16. [Environment Variables](#16-environment-variables)
17. [Running the Application](#17-running-the-application)
18. [Testing](#18-testing)
19. [Configuration](#19-configuration)
20. [Troubleshooting](#20-troubleshooting)
21. [Evaluation / Quality Metrics](#21-evaluation--quality-metrics)
22. [Limitations](#22-limitations)
23. [Future Roadmap](#23-future-roadmap)
24. [License](#24-license)
25. [Contributors](#25-contributors)

---

## 1. What is SourceLedger?

**SourceLedger** is an enterprise-grade AI Product Intelligence and Catalog Harmonization System. Built for industrial e-commerce, distributor onboarding, and catalog data engineering, SourceLedger ingests multi-format documents (PDF specification sheets, scanned catalog images, vendor web pages, raw text, and bulk CSV files) and transforms them into standardized, commerce-ready product records.

Unlike black-box AI tools that output unverified attributes, SourceLedger operates under a strict **Golden Rule**: *No product attribute exists in the catalog without a verifiable source citation, a 0–100% confidence score, and an explicit AI reasoning chain.* Low-confidence fields ($\le 70\%$) or cross-source conflicts are automatically routed to a human Review Queue, ensuring complete data governance.

---

## 2. Problem Statement

Industrial distributors and e-commerce platforms process millions of complex technical listings from thousands of manufacturers. Today, this workflows suffers from critical friction:

- **Unstructured & Disparate Sources**: Product specifications are trapped in multi-page PDF datasheets, unstructured vendor web pages, scanned image catalogs, and noisy CSV exports.
- **Inconsistent Taxonomy & Units**: Measurements (e.g., flow rate, voltage, thread size) are recorded in mixed units (GPM vs. m³/h, HP vs. kW) or fractional formats (3/8 in vs. 0.375 in).
- **Lack of Provenance & Trust**: Standard LLM extractions suffer from hallucinations, silently fabricating part numbers or attributes without audit trails.
- **Manual Review Bottlenecks**: Catalog managers spend hundreds of hours manually cross-checking spec sheets, leading to high onboarding costs and delayed time-to-market.

---

## 3. Solution Overview

SourceLedger resolves catalog chaos through a multi-agent orchestration pipeline that pairs multimodal vision LLMs with deterministic validation rules:

```text
  Input Documents (PDF / Web / Image / CSV / Text)
                         │
                         ▼
        ┌──────────────────────────────────┐
        │        Ingestion Agent           │  ──► SHA-256 Hashing & Storage
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │  Ledger Multimodal OCR Agent     │  ──► PyMuPDF / pypdfium2 Vision Rendering
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │        Extraction Agent          │  ──► Category Schema Locking (Pydantic)
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │        Enrichment Agent          │  ──► Secondary Gap-Fill & Taxonomy Mapping
        └────────────────┬─────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────┐
        │        Validation Agent          │  ──► Conflict Resolution & Confidence Scoring
        └────────────────┬─────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   Auto-Committed               Needs Review Queue
   (Confidence ≥ 70%)           (Human-in-the-Loop Audit Trail)
          │                             │
          └──────────────┬──────────────┘
                         │
                         ▼
           Standardized Delivery CSV Export
```

---

## 4. Key Features

- **Multi-Format Ingestion**: Ingests PDF specification sheets, web URLs/HTML, scanned document images, raw text, and bulk CSV files (`input/Unihack_ Sample Dataset - Input.csv`).
- **Ledger Multimodal OCR Agent**: Multi-page PDF page screenshot rendering using PyMuPDF (`fitz`) and `pypdfium2` fallback, capturing high-resolution vision extractions with page-level citations.
- **Domain-Specific Schema Locking**: Enforces category-specific Pydantic schemas across 6 industrial domains (`industrial_pump`, `electrical_connector`, `safety_fastener`, `power_tool`, `home_appliance`, `generic`).
- **Confidence Scoring & Trust-Tier Ranking**: Computes overall and field-level confidence scores (0–100%) incorporating source trust tiers (Tier 1 OEM Manufacturer, Tier 2 Authorized Distributor, Tier 3 Marketplace).
- **Field Inspector & Provenance**: Surfaces verbatim source excerpts, confidence badges, and LLM reasoning chains for every catalog field.
- **Human-in-the-Loop Review Queue**: Dedicated workflow for catalog managers to review, accept, edit, or reject flagged attributes with immutable `ReviewAction` audit logging.
- **Supabase Authentication**: Production authentication suite featuring email/password sign-up, email verification access guard, sign-in, password reset workflows, and Google OAuth 2.0.
- **Standardized Delivery CSV Exporter**: Exports catalog records into delivery CSV format (`output/Unihack_ Output - Delivery Format.csv`).

---

## 5. How SourceLedger Works

### File Ingestion & OCR
1. **Ingest Source**: Users upload files via the **Ingest New Source** modal or select **Ledger Multimodal OCR Agent**.
2. **Vision Preprocessor**: PDF documents are rendered into high-resolution PNG page screenshots (`screenshot_1.png`, `screenshot_2.png`, ...).
3. **Multimodal Extraction**: Multimodal vision models analyze page screenshots concurrently in parallel, extracting attributes into structured JSON.

### Extraction, Enrichment & Validation
1. **Schema Locking**: Extracted JSON is validated against Pydantic category models. Malformed responses trigger automatic JSON repair loops.
2. **Secondary Gap Fill**: The Enrichment Agent cross-references secondary sources and catalog entries to populate missing attributes.
3. **Trust & Conflict Resolution**: The Validation Agent compares conflicting values across sources, favoring higher trust tiers (Tier 1 OEM over Tier 3 Marketplace) unless confidence deltas warrant human review.
4. **Status Assignment**: Records with overall confidence $\ge 70\%$ are marked `auto_committed`; records with fields $< 70\%$ are routed to `needs_review`.

---

## 6. Multi-Agent Architecture

SourceLedger employs six specialized backend agents:

```text
                           ┌─────────────────────────┐
                           │      Orchestrator       │
                           └────────────┬────────────┘
                                        │
      ┌──────────────────┬──────────────┼──────────────┬──────────────────┐
      │                  │              │              │                  │
┌─────▼──────────┐ ┌─────▼────────┐ ┌───▼──────────┐ ┌─▼─────────────┐ ┌──▼────────────┐
│Ingestion Agent │ │Extraction    │ │Enrichment    │ │Validation   │ │Explainability│
│PDF/Web/CSV/Hash│ │Agent (Schema)│ │Agent (Taxon) │ │Agent (Trust)│ │Layer (Audits)│
└────────────────┘ └──────────────┘ └──────────────┘ └─────────────┘ └──────────────┘
```

1. **`IngestionAgent`** (`backend/src/agents/ingestion_agent.py`): Parses raw PDFs, HTML, text, and CSV files; generates unique SHA-256 content hashes for idempotency.
2. **`ExtractionAgent`** (`backend/src/agents/extraction_agent.py` & `multi_phase_extractor.py`): Executes category-locked LLM extractions against category schemas.
3. **`EnrichmentAgent`** (`backend/src/agents/enrichment_agent.py`): Fills missing attributes using secondary sources and maps UNSPSC/eCl@ss taxonomy codes.
4. **`ValidationAgent`** (`backend/src/agents/validation_agent.py`): Calculates weighted field and record confidence scores, resolves multi-source conflicts, and sets review statuses.
5. **`ExplainabilityLayer`** (`backend/src/agents/explainability_layer.py`): Annotates extracted fields with verbatim source text excerpts and LLM reasoning chains.
6. **`KeyRotator` / Gateway Client** (`backend/src/agents/main.py` & `backend/ocr_feature/ocr_agent/gateway_client.py`): Thread-safe round-robin rotator managing API keys to prevent HTTP 429 rate limit errors.

---

## 7. System Architecture

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                 │
│          React 18 + TypeScript + Vite + Tailwind CSS v4 + Motion          │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │ REST APIs / JSON
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                              FASTAPI BACKEND                              │
│         FastAPI Router + Async Handlers + Pydantic v2 Schema Engine        │
└──────────────────┬──────────────────┬──────────────────┬──────────────────┘
                   │                  │                  │
                   ▼                  ▼                  ▼
        ┌──────────────────┐┌──────────────────┐┌──────────────────┐
        │  Multi-Agent     ││ Persistent Store ││ Supabase Auth    │
        │  Orchestration   ││ SQLite DB        ││ Session & OAuth  │
        └──────────────────┘└──────────────────┘└──────────────────┘
```

---

## 8. Project Structure

```text
SourceLedger/
├── backend/
│   ├── ocr_feature/
│   │   ├── ocr_agent/
│   │   │   ├── agent.py               # Multimodal OCR Agent system
│   │   │   ├── gateway_client.py      # LLM Gateway client & fallback router
│   │   │   ├── prompts.py             # Vision OCR prompt templates
│   │   │   ├── schemas.py             # OCR Pydantic models
│   │   │   └── tools.py               # Preprocessing & fallback extractors
│   │   └── tests/                     # OCR pytest suite
│   ├── src/
│   │   ├── agents/                    # Multi-agent system implementations
│   │   │   ├── enrichment_agent.py    # Enrichment & taxonomy agent
│   │   │   ├── explainability_layer.py# Provenance & citation layer
│   │   │   ├── extraction_agent.py    # Schema-locked extraction agent
│   │   │   ├── ingestion_agent.py     # Document ingestion agent
│   │   │   └── validation_agent.py    # Validation & confidence scoring agent
│   │   ├── api/                       # FastAPI router endpoints
│   │   │   ├── routes_dashboard.py    # Dashboard metrics endpoint
│   │   │   ├── routes_export.py       # Delivery CSV export endpoint
│   │   │   ├── routes_fields.py       # Field approval & override endpoints
│   │   │   ├── routes_ingest.py       # Multi-agent ingestion endpoint
│   │   │   ├── routes_ocr.py          # Vision OCR endpoint
│   │   │   ├── routes_products.py     # Catalog products endpoints
│   │   │   └── routes_review.py       # Review queue endpoints
│   │   ├── db/                        # Persistence layer (SQLite + Supabase)
│   │   │   ├── store.py               # SQLite persistent product store
│   │   │   └── supabase_client.py     # Supabase DB integration client
│   │   ├── models/                    # Domain models & category schemas
│   │   │   ├── product_record.py      # Core ProductRecord & ProductField models
│   │   │   └── schemas.py             # Category schema registry
│   │   ├── services/                  # Business logic & CSV exporters
│   │   │   └── csv_processor.py       # CSV batch processing & delivery exporter
│   │   ├── config.py                  # Environment settings manager
│   │   └── main.py                    # FastAPI application entry point
│   ├── requirements.txt               # Backend Python dependencies
│   └── sourceledger.db                # Persistent SQLite database file
├── frontend/
│   ├── src/
│   │   ├── components/                # React UI view components
│   │   │   ├── auth/                  # Supabase authentication screens
│   │   │   ├── CatalogHealthTrendChart.tsx
│   │   │   ├── ConfidenceHeatmap.tsx
│   │   │   ├── DashboardView.tsx
│   │   │   ├── FieldInspectorView.tsx
│   │   │   ├── IngestModal.tsx
│   │   │   ├── IngestionSourcesView.tsx
│   │   │   ├── OcrAgentView.tsx
│   │   │   ├── ProductsCatalogView.tsx
│   │   │   └── ReviewQueueView.tsx
│   │   ├── context/                   # AuthContext provider & hooks
│   │   ├── lib/                       # API client & Supabase SDK client
│   │   ├── App.tsx                    # Main layout & navigation router
│   │   └── main.tsx                   # React root entry point
│   ├── package.json                   # Frontend Node dependencies & scripts
│   └── vite.config.ts                 # Vite bundler configuration
├── docs/                              # Project architecture & PRD documentation
├── input/                             # Sample input datasets
├── output/                            # Generated output CSV files
├── docker-compose.yml                 # Docker service composition skeleton
├── run_batch_processing.py            # CLI script for bulk CSV batch processing
├── start.sh                           # Unified startup & verification script
├── .env.example                       # Root environment variables template
├── CHANGELOG.md                       # Release & feature changelog
└── README.md                          # Master documentation
```

---

## 9. Technology Stack

| Layer | Technology | Purpose / Usage |
|---|---|---|
| **Frontend UI** | React 18 + TypeScript | Component-based web application with strict type safety |
| **Build Tool** | Vite | Ultra-fast HMR dev server and production asset bundler |
| **Styling & Motion** | Tailwind CSS v4 + Motion | Glassmorphic design system and smooth micro-animations |
| **Charts & Icons** | Recharts + Lucide React | Data visualization charts and UI icons |
| **Authentication** | Supabase Auth (`@supabase/supabase-js`) | Zero-trust email/password & Google OAuth 2.0 authentication |
| **Backend API** | FastAPI + Uvicorn | High-performance async REST API framework |
| **Schema Engine** | Pydantic v2 + Pydantic Settings | Category schema locking and environment configuration |
| **Document OCR** | PyMuPDF (`fitz`), pypdfium2, Pillow | High-resolution PDF rendering and image pre-processing |
| **Database** | SQLite (`sourceledger.db`) + Supabase | Local persistent store with optional Supabase Cloud sync |
| **AI / LLM** | Google Gemini API / API Gateway | Multimodal vision & structured text extraction |
| **CSV Engine** | Pandas + Python `csv` module | Delivery format CSV generation (`Unihack_ Output - Delivery Format.csv`) |
| **Testing** | Pytest + Pytest-Asyncio | Automated backend unit and integration test suite |

---

## 10. API Reference

**Base URL**: `http://localhost:8000/api`  
**Swagger UI**: `http://localhost:8000/docs`  
**ReDoc**: `http://localhost:8000/redoc`

| Endpoint | Method | Description |
|---|---|---|
| `/api/ingest` | `POST` | Ingest PDF, web URL/HTML, raw text, or CSV through multi-agent pipeline |
| `/api/extract` | `POST` | Multimodal Vision OCR extraction for document images/PDFs |
| `/api/products` | `GET` | List catalog product records with optional status/category filters |
| `/api/products/{id}` | `GET` | Retrieve detailed product record including fields and audit log |
| `/api/fields/approve` | `POST` | Approve single field or all fields for a product record |
| `/api/fields/edit` | `POST` | Override an attribute value and log a `ReviewAction` entry |
| `/api/review` | `GET` | Retrieve all fields currently flagged `needs_review` |
| `/api/dashboard/stats` | `GET` | Fetch catalog metrics, category confidence breakdown, and recent activity |
| `/api/export/csv` | `GET` | Export catalog data as a delivery CSV file matching Unihack specifications |

---

## 11. Database

SourceLedger uses a dual-layer persistence strategy:

1. **SQLite Database (`backend/sourceledger.db`)**: Primary zero-config persistent store. Stores all ingested sources, product records, fields, and review actions. Survives server restarts.
2. **Supabase Postgres (Cloud Sync)**: Optional cloud synchronization via `sync_product_to_supabase()` in `backend/src/db/supabase_client.py`.

### Primary Tables (`sourceledger.db`)
- `sources`: `id` (UUID), `content_hash` (TEXT), `data` (JSON), `created_at` (TIMESTAMP)
- `products`: `id` (UUID), `category` (TEXT), `name` (TEXT), `confidence` (INTEGER), `data` (JSON), `updated_at` (TIMESTAMP)
- `review_actions`: `id` (UUID), `product_id` (UUID), `data` (JSON), `created_at` (TIMESTAMP)

---

## 12. Authentication & Security

Authentication is powered by **Supabase Auth** (`frontend/src/context/AuthContext.tsx`):

- **Email & Password Authentication**: Full sign-up, sign-in, and verification access guard.
- **Email Verification Guard**: Unconfirmed accounts are restricted by `VerifyEmailView.tsx`.
- **Google OAuth 2.0**: Integrated Google single sign-on (`signInWithGoogle()`).
- **Password Reset Flow**: Request password recovery (`ForgotPasswordView.tsx`) and set new passwords (`ResetPasswordView.tsx`).
- **Security & Key Protection**: All LLM API keys remain strictly on the backend server. SHA-256 document hashing ensures content idempotency.

---

## 13. Prerequisites

- **Python**: Version `3.10` or higher (`3.12` recommended)
- **Node.js**: Version `18.0` or higher (`24.x` supported)
- **npm**: Version `9.0` or higher

---

## 14. Quick Start

Run the automated one-liner script from the project root:

```bash
chmod +x start.sh
./start.sh
```

The script automatically:
1. Verifies system prerequisites (Python, Node, npm).
2. Sets up Python virtual environment (`backend/.venv`) and installs dependencies.
3. Installs frontend Node modules (`frontend/node_modules`).
4. Creates default `.env` files from `.env.example` templates.
5. Launches FastAPI backend on `http://localhost:8000` and Vite frontend on `http://localhost:3000`.

---

## 15. Manual Installation

### Backend Setup
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env
npm run dev -- --port 3000
```

---

## 16. Environment Variables

### Root / Backend `.env` (`backend/.env`)
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GOOGLE_API_KEY1` .. `8` | Optional | `""` | Gemini API keys for multi-key round-robin rotator |
| `API_URL` | Required | `https://free-api-erel.onrender.com/api/generate` | Gateway proxy URL for model requests |
| `API_KEY` | Required | `sk_proxy_qu7f0n...` | Gateway proxy authentication key |
| `CONFIDENCE_THRESHOLD` | Optional | `70` | Threshold below which fields route to Review Queue |
| `SOURCE_STORAGE_PATH` | Optional | `./storage/sources` | Storage path for ingested source documents |
| `SUPABASE_URL` | Optional | `""` | Supabase project URL for database cloud sync |
| `SUPABASE_KEY` | Optional | `""` | Supabase API key for database cloud sync |

### Frontend `.env` (`frontend/.env`)
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `VITE_SUPABASE_URL` | Required | `https://your-project-id.supabase.co` | Supabase project URL for authentication |
| `VITE_SUPABASE_ANON_KEY` | Required | `your-supabase-anon-key-here` | Supabase public anon key for authentication |

---

## 17. Running the Application

- **Web Application**: Access `http://localhost:3000` in your browser.
- **Backend API**: Access `http://localhost:8000/api` or explore interactive Swagger docs at `http://localhost:8000/docs`.
- **CLI Batch Processing**: Run `python3 run_batch_processing.py` to bulk-process sample dataset files in `input/` and generate output CSVs in `output/`.

---

## 18. Testing

### Run Backend Pytest Suite
```bash
# Run core backend agent test suite
python3 -m pytest backend/tests

# Run OCR agent test suite
python3 -m pytest backend/ocr_feature/tests
```

### Run Frontend Type Check
```bash
cd frontend
npm run lint
```

---

## 19. Configuration

- **Confidence Threshold**: Modify `CONFIDENCE_THRESHOLD=70` in `backend/.env` to adjust the auto-commit sensitivity.
- **Supported Categories**: Extended schemas can be defined in `backend/src/models/schemas.py`.

---

## 20. Troubleshooting

- **500 OCR Agent Configuration Error**: Ensure `pillow`, `pymupdf`, `pypdfium2`, and `jinja2` are installed in `backend/.venv`.
- **CORS / Connection Refused**: Confirm FastAPI backend is running on `http://localhost:8000`.
- **Supabase Auth Redirect Error**: Add `http://localhost:3000` to Site URL and Redirect URLs under **Supabase Dashboard -> Authentication -> URL Configuration**.

---

## 21. Evaluation / Quality Metrics

- **Pipeline Velocity**: Single-item extraction completes in under 3 seconds using parallel vision page concurrency.
- **Schema Compliance**: 100% Pydantic schema validation rate across all 6 industrial domain models.
- **Provenanced Output**: Every extracted attribute carries a verbatim quote, confidence score, and LLM reasoning chain.

---

## 22. Limitations

- **Vector Database**: Qdrant vector embedding service is configured as a Phase 5 stretch architecture and disabled by default.
- **OCR Scan Quality**: Highly degraded or low-resolution handwritten scans are processed best-effort and flagged for human review.

---

## 23. Future Roadmap

- [ ] **Vector Similarity Deduplication**: Enable Qdrant vector embeddings for clustering duplicate catalog listings across suppliers.
- [ ] **UNSPSC Automated Taxonomy Mapping**: Expand automated UNSPSC/eCl@ss code lookups across specialized sub-categories.
- [ ] **Active Learning Loop**: Feed `ReviewAction` human corrections back into prompt refinement pipelines.

---

## 24. License

Licensed under the [Apache License, Version 2.0](LICENSE).

---

## 25. Contributors

- **Balaraj R** — Founder
- **Bharath CD** — Co-founder

---

*This README reflects the current implementation of SourceLedger and is maintained alongside codebase updates.*
