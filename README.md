# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Authors & Developers**: **Rajeev Karakoti**, **Priyanshu Saklani**, **Prasanna Godiyal**  
> **Status**: ✅ **Levels 0, 1, 1.5, 2, 3, 4, 5 & 6 Complete — Viva & Production Ready**  
> **Dataset**: Olist Brazilian E-Commerce (~100,000 orders, 7 tables, Currency: `R$`)  
> **Repository**: [InsightForge-AI-Powered-Autonomous-Business-Intelligence-Analyst](https://github.com/rajeevv4/InsightForge-AI-Powered-Autonomous-Business-Intelligence-Analyst)

---

## 🎓 Viva & Project Presentation Quick Reference

For examiners, evaluators, and project presentations, read the dedicated **[Viva Preparation Guide](docs/viva_preparation.md)** containing:
- Executive problem statement and comparison with naive Text-to-SQL.
- Comprehensive breakdown of the **4 Non-Negotiable Core Engineering Pillars**.
- Complete canonical benchmarks table ($R\$ 13.22M$ product revenue, $R\$ 15.42M$ gross revenue, $96,478$ delivered orders, $R\$ 159.83$ AOV).
- **25+ Technical Viva Questions & In-Depth Answers** covering indexing, SQL CTE fan-out fixes, grounding verification, and slowapi rate limiting.
- **5-Minute Live Viva Demo Script** with step-by-step talk tracks.

---

## 📌 Executive Summary

**InsightForge** is an enterprise-grade autonomous Business Intelligence analyst platform. It transforms natural-language business questions into data-backed executive insights, interactive visualizations, zero-hallucination grounded explanations, and automated data quality audits.

Built on top of the **Olist Brazilian E-Commerce Dataset** inside **PostgreSQL 15+** (Docker Compose & CI use `postgres:15-alpine`; also verified on PostgreSQL 16 locally and 17 on Supabase), InsightForge enforces a strict architectural boundary between AI reasoning and database analytics: the LLM never receives database credentials, never executes arbitrary SQL, and all numerical outputs are verified by a deterministic Grounding Verifier against computed PostgreSQL evidence before reaching the user.

---

## 🚀 Project Levels & Implementation Status

| Level | Focus Area | Status | Key Deliverables & Engineering Achievements |
|---|---|:---:|---|
| **Level 0** | **Correctness & Mathematical Soundness** | ✅ **COMPLETE** | • **Eliminated Join Fan-Out**: Order-level review CTE in `views.sql` ensures category contribution strictly sums to $100.00\%$ and product revenue equals canonical $R\$ 13,221,498.11$.<br>• **Real Data Quality Audits**: Replaced hardcoded strings with computed PK uniqueness, FK integrity, domain bounds, and join safety audits.<br>• **BRL Standard**: Unified currency symbol to $R\$$ throughout charts, KPI cards, and heuristic answers.<br>• **Robust Intent Routing**: Word-boundary regex matching prevents false positives on sub-words.<br>• **Engine Pooling**: Module-level pooled SQLAlchemy engine (`pool_pre_ping=True`). |
| **Level 1** | **Infrastructure for AI Features & Defense** | ✅ **COMPLETE** | • **Read-Only Database Role**: `insightforge_ro` role with SELECT-only grants and `statement_timeout = '5s'`.<br>• **AI Audit Logging**: `AIAuditService` persisting question, intent, latency, route, success flag, and error with `GET /api/ai/history`.<br>• **Golden Evaluation Suite**: 113 benchmark questions in `golden_questions.yaml` (83 intent cases + 30 Text-to-SQL cases) scored by CLI `run_eval.py` (**97.59% intent accuracy**, **100.00% numeric faithfulness** on the live DB).<br>• **Grounding Verifier**: Regex token parser in `grounding.py` matching numbers against evidence within $\pm 0.05$ / $1.5\%$ with heuristic fallback.<br>• **API Rate Limiting**: `slowapi` limiter protecting `/api/ai/ask` (default 30/min).<br>• **Docker & CI/CD**: Multi-container `docker-compose.yml` and automated GitHub Actions CI workflow. |
| **Level 1.5** | **Removal of Silent Fixture Fallbacks & Truthful Health** | ✅ **COMPLETE** | • **Zero Silent Fake Data**: Eliminated automatic canonical fallbacks; services raise `DatabaseUnavailableError` unless `USE_FIXTURES=1`.<br>• **HTTP 503 Service Unavailable**: Endpoints return standard 503 `"Database unavailable"` when DB is down.<br>• **Truthful Health & Data Source**: `/api/health` returns `data_source: "postgres" \| "fixture"` and reports `database: "disconnected"` truthfully.<br>• **UI DEMO DATA Badge**: Header displays prominent amber `"DEMO DATA"` badge when operating on fixtures.<br>• **Frontend ErrorBanner**: UI displays `ErrorBanner` on 503s instead of empty/fabricated charts.<br>• **Dual-Mode Eval CLI**: `run_eval.py` supports `--mode heuristic` and `--mode gemini`. |
| **Level 2** | **Deterministic Multi-Method Anomaly Detection** | ✅ **COMPLETE** | • **Deterministic Engine**: 4 mathematical detection methods (Rolling MAD Robust Z-score, STL decomposition residuals, IQR dimension slices, and IsolationForest multivariate daily vectors).<br>• **Rule 4 & 5 Compliant**: Detection operates purely on real PostgreSQL delivered orders; LLM never detects anomalies.<br>• **Known Event Catalog**: Dynamic labelling of historical shopping holidays (e.g., Nov 2017 Black Friday) as `known_event_candidate` without hardcoded revenue.<br>• **IsolationForest Guardrail**: Requires consensus with univariate methods or marks severity as `low` to avoid spurious false positives.<br>• **REST API & UI**: `GET /api/anomalies`, rate-limited `POST /api/anomalies/scan`, and interactive React Anomalies dashboard with Recharts markers and severity filters. |
| **Level 3** | **Guarded Text-to-SQL with Semantic Guardrails** | ✅ **COMPLETE** | • **Hybrid Routing Policy**: High-confidence requests ($\ge 0.80$) execute via deterministic intent views; free-form queries route to Guarded Text-to-SQL.<br>• **AST Security Validator**: Built on `sqlglot` AST parsing (not regex): strictly enforces single statement, SELECT-only, function/schema denylist (`pg_sleep`, `pg_catalog`), analytical table allow-list, Cartesian join prohibition, fan-out join rejection, and automatic `LIMIT <= 500`.<br>• **Read-Only Sandbox Execution**: Runs strictly through `insightforge_ro` (5s timeout) with `REVOKE SELECT ON ai_audit_log`.<br>• **Self-Correction Retry Loop**: Automated error diagnosis and AST re-prompting (max 2 retries) upon syntax or schema violations.<br>• **Grounded LLM Explanations**: Regex numeric faithfulness check on generated explanations against returned SQL rows.<br>• **Interactive UI**: "Show SQL" inspection modal, dynamic data table, and automatic Recharts visualization suggestions. |
| **Level 4** | **Hindi + English Voice Input & Resilient Fallback** | ✅ **COMPLETE** | • **Multimodal Audio Endpoint**: `POST /api/voice/transcribe` with in-memory buffer, MIME normalization (stripping `codecs=opus`), container magic-byte verification, and zero audio persistence.<br>• **Voice Quota Defense (503)**: Catches Gemini 429 quota exhaustion and returns clean HTTP 503 without leaking stack traces or raw JSON.<br>• **Browser Web Speech API Fallback**: Resilient fallback to browser SpeechRecognition (`hi-IN` / `en-IN` based on language selector) whenever backend voice is unavailable.<br>• **UI States & Timer**: Live countdown timer (`0:00 / 1:00`), recording pulse, transcribing spinner, editable question box, and speech language toggle.<br>• **Devanagari & Scale Grounding**: Devanagari digit translation (`०-९` $\rightarrow$ `0-9`) and South Asian numeric scale normalization (`lakh`/`लाख`, `crore`/`करोड़`). |
| **Level 5 & 5.1** | **Dataset Workspace & Adversarial Ingestion Hardening** | ✅ **COMPLETE** | • **Multi-File Ingestion**: Safely parses CSV, TSV, and XLSX into dedicated `ds_<8hex>` schemas with quoted SQL identifiers (`psycopg2.sql.Identifier`).<br>• **Adversarial Ingestion Armor**: Rejects decompression zip bombs, ragged rows, formula injections (`=`, `+`, `-`, `@`), oversized payloads (>25MB), and directory traversal attacks.<br>• **Deterministic Profiling (Zero LLM)**: Instant computation of distinct counts, null %, min/max, numeric moments, and auto-inferred analytical roles (`id`, `datetime`, `measure`, `dimension`, `boolean`).<br>• **Multi-Format Datetime Engine**: Detects ISO, dd/mm vs mm/dd ambiguity flags, 12h AM/PM, month names, epoch s/ms, and Excel serial dates.<br>• **Multi-Table FK Inference**: Inferred 1:1 and 1:N relationships via $\ge 95\%$ containment graph.<br>• **Owner Isolation & Cleanup**: SHA-256 hashed owner tokens on all endpoints; automated cleanup daemon (`scripts/cleanup_datasets.py`) dropping expired schemas. |
| **Level 6 & 6.1** | **Dataset-Aware Q&A, Semantic Layer & Cross-Dataset Defense-in-Depth** | ✅ **COMPLETE** | • **Deterministic Semantic Layer**: `insightforge.dataset_semantic` storing measures, dimensions, aggregations, and starter questions with draft/confirm review.<br>• **AST Cross-Dataset Scoping**: Scoped `sqlglot` AST validator requiring strict schema qualification (`ds_<8hex>.table`), blocking cross-dataset queries, shadow CTE aliases, unclosed comments, and dangerous functions (`dblink`, `to_regclass`, `current_setting`, `query_to_xml`).<br>• **Database Role Defense-in-Depth**: Dynamic NOLOGIN role `dsr_<8hex>` with `USAGE`/`SELECT` granted to `insightforge_ro`; queries run under `SET LOCAL ROLE dsr_<8hex>` + `SET LOCAL search_path`.<br>• **Privacy Scoping (`share_samples=False`)**: Zero cell values or canaries leak into prompts, retries, summaries, or audit logs; PostgreSQL errors sanitized.<br>• **Quick Insights & Time-Trend Anomaly Detection**: Automated pre-computed top-N and time-trend queries plus rolling MAD anomaly detection on custom datasets.<br>• **Generality & Verification**: Evaluated across 3 benchmark domains; offline unit suite (277 tests) and live integration suite (25 tests) passing. |

---

## 🔍 Deep-Dive: What We Implemented vs. How We Implemented It

InsightForge adheres to strict, production-grade engineering principles. The table below details **what** was implemented and **how** it was engineered under the hood across each major subsystem:

| System Pillar | What We Implemented | How We Implemented It (Under the Hood) |
|---|---|---|
| **1. Correctness & Fan-Out Prevention** | • Correct $R\$ 13.22M$ product revenue and $R\$ 15.42M$ gross revenue.<br>• Category contribution sums to strictly $100.00\%$.<br>• $96,478$ delivered orders counted. | • **Order-level CTE in `views.sql`**: Isolated `order_reviews` and `order_payments` into subqueries before joining `order_items`. This prevents Cartesian row multiplication that inflated revenue by up to $18\%$.<br>• Strict delivered-order filtering (`order_status = 'delivered'`) applied exclusively to financial KPIs. |
| **2. Role Separation & Database Security** | • Read-only sandboxed role `insightforge_ro`.<br>• Statement timeouts preventing DoS.<br>• Zero credentials exposed to LLM. | • PostgreSQL `insightforge_ro` role created with `CONNECT`, `USAGE`, and `SELECT` granted only on analytical views and tables.<br>• Hard `statement_timeout = '5s'` configured at role level.<br>• `REVOKE SELECT ON insightforge.ai_audit_log FROM insightforge_ro` prevents LLM from inspecting user query history. |
| **3. Grounding Verification (Zero Hallucination)** | • Every numeric figure in AI narratives is verified before being shown to users.<br>• Unverified answers trigger deterministic fallback. | • **Regex Token Parser (`grounding.py`)**: Extracts numeric literals and percentages from generated text.<br>• Compares numbers against computed SQL evidence rows within absolute tolerance $\pm 0.05$ or relative tolerance $\pm 1.5\%$.<br>• Normalizes Devanagari digits (`०-९` $\rightarrow$ `0-9`) and South Asian scales (`lakh` $\rightarrow \times 10^5$, `crore` $\rightarrow \times 10^7$).<br>• On mismatch, drops LLM narrative and synthesizes grounded heuristic summary. |
| **4. Guarded Text-to-SQL & AST Security** | • Safe conversion of natural-language questions into PostgreSQL queries for Olist.<br>• Self-correction loop on errors. | • **`sqlglot` AST Validator (`sqlvalidator.py`)**: Inspects parse tree rather than regex. Enforces exactly 1 statement, SELECT/UNION only, and checks against allowed views.<br>• Denies `pg_*` catalogs, `information_schema`, system functions (`pg_sleep`, `query_to_xml`, `dblink`), and CTE alias shadowing.<br>• Enforces `LIMIT <= 500`.<br>• Self-correction feeds sanitized syntax/schema error back to LLM for up to 2 retries. |
| **5. Multilingual Voice & Web Speech Fallback** | • Voice transcription for Hindi (Devanagari), Hinglish, and English.<br>• Zero persistent audio storage.<br>• Seamless browser fallback on quota limits. | • **Ephemeral In-Memory Buffer (`voice_service.py`)**: Audio processed in memory via Gemini API; audio bytes are never written to disk or database.<br>• **MIME & Container Normalization**: Strips `codecs=...` parameters, validates magic bytes (WebM EBML, WAV RIFF, MP4 ftyp, OGG OggS), and rejects non-audio.<br>• **Graceful 503 Handling**: Maps Gemini 429 quota errors to HTTP 503 with clean user messages.<br>• **Web Speech API Fallback (`AskInsightForge.tsx`)**: In parallel with audio recording, browser `SpeechRecognition` captures speech. If backend returns non-200, transcript immediately fills input box with `hi-IN` or `en-IN` support. |
| **6. Multi-Tenant Dataset Workspace** | • User uploads of custom CSV, TSV, XLSX datasets.<br>• Per-upload schema isolation.<br>• Auto-profiling & quality findings. | • **Isolated Schemas (`ds_<8hex>`)**: Created dynamically per upload in PostgreSQL.<br>• **PostgreSQL `COPY` Ingestion**: Fast bulk ingestion using `psycopg2.sql.Identifier` quoting against SQL injection.<br>• **Adversarial Armor**: Decompression bomb zip inspection, CSV formula neutralization (strips `=,+,-,@`), and ragged row rejection.<br>• **Zero-LLM Statistical Profiling**: Fast Pandas moments, null %, distinct counts, and role heuristics (`id`, `datetime`, `measure`, `dimension`).<br>• **Multi-Format Datetime Inference**: Recognizes ISO 8601, dd/mm vs mm/dd ambiguity, 12h AM/PM, month names, epoch timestamps, and Excel serial dates.<br>• **Containment FK Inference**: Inferred join candidates with $\ge 95\%$ containment. |
| **7. Cross-Dataset Defense-in-Depth & Privacy** | • Users asking questions on Dataset A can never read Dataset B.<br>• Zero cell value leakage under strict privacy.<br>• Automated cleanup of expired data. | • **Dedicated NOLOGIN Roles (`dsr_<8hex>`)**: PostgreSQL role created per schema, granted `USAGE` on schema and `SELECT` on its tables, and granted to `insightforge_ro`.<br>• **Query Isolation**: Queries executed with `SET LOCAL ROLE "dsr_<8hex>"` and `SET LOCAL search_path = "{schema_name}", public`. Database engine hard-blocks cross-schema queries with `permission denied for schema`.<br>• **Privacy Scoping (`share_samples=False`)**: Prompts receive table/column schema only; zero data rows, cell values, or canary strings reach LLM. PostgreSQL error messages sanitized to strip literals and keys.<br>• **In-Memory Cache Scoping**: Cache keyed strictly by `(dataset_id, question.lower())`.<br>• **Automated Daemon (`cleanup_datasets.py`)**: Purges expired schemas (`ds_%`) and drops associated roles (`dsr_%`). |
| **8. Multi-Method Anomaly Detection** | • Deterministic detection of sales spikes, fulfillment drops, and outliers.<br>• Zero hallucination, zero LLM anomaly labelling. | • **4 Complementary Statistical Methods (`anomaly_service.py`)**:<br>  1. *Rolling Median Absolute Deviation (MAD)*: Robust Z-score on 14-day rolling window.<br>  2. *Seasonal-Trend Decomposition (STL)*: LOESS residuals identifying trend breaks.<br>  3. *Interquartile Range (IQR)*: Outlier detection across dimensional slices.<br>  4. *IsolationForest*: Multivariate daily vectors (revenue, orders, freight, delivery days).<br>• Dynamic labelling of historical shopping holidays (Black Friday candidate) without hardcoded revenue values. |

---

## 🏗 System Architecture & Directory Structure

```
InsightForge/
├── .github/
│   └── workflows/
│       └── ci.yml                    # Automated GitHub Actions CI workflow (DB, tests, evals, build)
├── backend/
│   ├── Dockerfile                    # Multi-stage Python 3.12 backend container build
│   ├── app/
│   │   ├── main.py                   # FastAPI application entry point & rate limit exception handler
│   │   ├── config.py                 # Pydantic BaseSettings (DB, Gemini, Rate Limits)
│   │   ├── database.py               # Read-write and read-only connection pooling
│   │   ├── limiter.py                # SlowAPI client IP rate limiter instance
│   │   ├── exceptions.py             # Custom DatabaseUnavailableError exception
│   │   ├── fixture_guard.py          # Rule 5 guard: NO silent fake data without USE_FIXTURES=1
│   │   ├── schemas/                  # Pydantic validation schemas
│   │   │   ├── ai.py                 # AskAIRequest, AskAIResponse, AIAuditLogItem
│   │   │   ├── anomaly.py            # AnomalyItem, TimeSeriesPoint, ScanRequest/Response
│   │   │   ├── dataset.py            # Level 5 Dataset upload, profile & findings schemas
│   │   │   ├── dataset_semantic.py   # Level 6 Semantic layer, ask & insights schemas
│   │   │   ├── kpis.py               # KPISummaryResponse schema
│   │   │   └── voice.py              # VoiceTranscribeResponse schema
│   │   ├── services/                 # Business logic service layer
│   │   │   ├── analytics_service.py  # Trusted analytics functions
│   │   │   ├── anomaly_service.py    # Deterministic anomaly detection (MAD, STL, IQR, IsolationForest)
│   │   │   ├── data_quality_service.py # 10-check data quality audit engine
│   │   │   ├── dataset_service.py    # Level 5 Dataset ingestion, profiling & schema lifecycle
│   │   │   ├── dataset_file_parser.py# File validation, CSV/XLSX parsing & formula neutralization
│   │   │   ├── dataset_semantic_service.py # Level 6 Semantic modeling & starter question generator
│   │   │   ├── dataset_insights_service.py # Level 6 Template insights & time-series anomaly detection
│   │   │   ├── ai_analytics_router.py # Controlled intent-to-view router
│   │   │   ├── ai_service.py         # Gemini classifier & grounded synthesizer (Hindi, Hinglish, English)
│   │   │   ├── sql_validator.py      # sqlglot AST SQL injection & safety validator (scoped context)
│   │   │   ├── text_to_sql_service.py# Guarded Text-to-SQL engine with self-correction & privacy engine
│   │   │   ├── audit_service.py      # AI interaction audit logger
│   │   │   ├── grounding.py          # Deterministic regex numeric faithfulness & Indian scale verifier
│   │   │   └── voice_service.py      # Gemini audio transcription & in-memory MIME validator
│   │   └── routers/                  # Modular REST API endpoints
│   │       ├── health.py             # Health check endpoint
│   │       ├── kpis.py               # Canonical KPI summary endpoint
│   │       ├── analytics.py          # Category, revenue, state, seller, delivery endpoints
│   │       ├── data_quality.py       # Data quality audit endpoint
│   │       ├── anomalies.py          # GET /api/anomalies & POST /api/anomalies/scan
│   │       ├── ai.py                 # POST /api/ai/ask, POST /api/ai/sql-ask & GET /api/ai/history
│   │       ├── voice.py              # POST /api/voice/transcribe (rate-limited, zero-persistence)
│   │       └── datasets.py           # Level 5 & 6 /api/datasets endpoints (upload, ask, semantic, insights)
│   ├── evals/
│   │   ├── golden_questions.yaml     # 113 structured evaluation test cases (intent, SQL & multilingual)
│   │   ├── run_eval.py               # Dual-mode benchmark (--mode heuristic | gemini | sql)
│   │   ├── dataset_eval.py           # Level 6 Generality evaluation harness for custom datasets
│   │   └── .cache/                   # Persistent evaluation cache for LLM quota protection
│   ├── tests/                        # 277 hermetic unit tests
│   │   ├── test_api.py               # Core REST API endpoint tests
│   │   ├── test_ai_api.py            # AI router, history, rate-limiting & fallback tests
│   │   ├── test_anomalies.py         # Multi-method anomaly detection & Black Friday tests
│   │   ├── test_sql_security.py      # Level 3 AST validator, SQL injection & routing tests
│   │   ├── test_grounding.py         # Grounding verifier, Devanagari & scale tests
│   │   ├── test_audit_service.py     # AI audit logging & ring-buffer tests
│   │   ├── test_fixture_guard.py     # Rule 5 fixture enforcement tests
│   │   ├── test_database_unavailable.py # Level 1.5 DB down 503 and fixture badge tests
│   │   ├── test_voice_multilingual.py # Level 4 Voice audio, MIME, Hindi NLP & TTS tests
│   │   ├── test_dataset_workspace.py # Level 5 File parser, role heuristic, relationship tests
│   │   ├── test_datasets_api.py      # Level 5 Dataset REST endpoints unit tests
│   │   └── test_dataset_qa.py        # Level 6 Scoped Text-to-SQL, privacy, & fan-out unit tests
│   └── tests_integration/            # Live database integration tests
│       ├── test_datasets_live.py     # Level 5 Real multi-tenant schema upload & cleanup
│       └── test_dataset_qa_live.py   # Level 6 Live multi-table semantic QA & insights
├── database/
│   ├── schema.sql                    # PostgreSQL DDL schema & table constraints
│   ├── views.sql                     # Analytical views with CTE fan-out prevention
│   ├── roles.sql                     # Read-only role (insightforge_ro) with 5s timeout
│   ├── migrations/                   # Database migrations (001, 002 for dataset_semantic)
│   ├── seed.py                       # Data cleaning & bulk CSV loader
│   ├── data_quality.py               # 10-check database audit script
│   ├── analytics.py                  # Pooled analytics execution module
│   └── test_analytics.py             # Analytics mathematical invariant test suite
├── docker-compose.yml                # Multi-container orchestration (Postgres, Backend, Frontend)
├── frontend/                         # React 18 + TypeScript + Vite + Tailwind BI Dashboard
│   ├── Dockerfile                    # Node 20 build + Nginx production container
│   ├── src/
│   │   ├── components/               # Visual charts & cards (BRL / R$ formatted)
│   │   │   ├── navigation/Sidebar.tsx# Navigation drawer & layout
│   │   │   ├── AskInsightForge.tsx   # Interactive AI Query Component
│   │   │   ├── CategoryChart.tsx     # Product category contribution bar chart
│   │   │   ├── RevenueTrendChart.tsx # Monthly sales & MoM growth trend
│   │   │   ├── StateChart.tsx        # Geographic state revenue distribution
│   │   │   ├── SellerChart.tsx       # Merchant fulfillment & revenue
│   │   │   ├── PaymentChart.tsx      # Payment method breakdown
│   │   │   └── DataQualityCard.tsx   # Live data quality audit status
│   │   ├── pages/                    # React Router (v7) page routes
│   │   │   ├── OverviewPage.tsx      # Executive KPIs & performance summary
│   │   │   ├── AskPage.tsx           # Natural-language AI analyst query interface
│   │   │   ├── AnalyticsPage.tsx     # Deep-dive analytical views
│   │   │   ├── DataQualityPage.tsx   # 10-point data quality audit dashboard
│   │   │   └── SettingsPage.tsx      # Application & database settings
│   │   └── services/api.ts           # Centralized Axios API client
├── semantic/                         # Single Source of Truth Semantic Layer
│   ├── business_glossary.yaml        # Standardized terms & business synonyms
│   ├── metrics.yaml                  # Canonical metric formulas & benchmark targets
│   ├── dimensions.yaml               # 9 analytical dimensions catalog
│   ├── relationships.yaml            # Join graph & fan-out multiplication rules
│   ├── validate_semantic_layer.py    # Semantic YAML validation suite
│   └── test_semantic_layer.py        # Semantic unit tests
├── docs/                             # Technical Documentation
│   ├── viva_preparation.md           # Complete Viva Presentation & Examination Defense Guide
│   ├── ai_infrastructure.md          # Level 1 AI Infrastructure Architecture Guide
│   ├── ai_integration.md             # AI integration architecture & grounding rules
│   ├── backend_api.md                # Complete REST API reference
│   ├── architecture.md               # System architecture breakdown
│   ├── database_schema.md            # Database schema dictionary & ETL rules
│   └── semantic_layer.md             # Semantic layer architecture guide
├── requirements.txt                  # Python dependencies
└── README.md                         # Project documentation
```

---

## 🛡 Security & Grounding Verification Architecture

```
User Question
     │
     ▼
[SlowAPI Rate Limiter (30/min)]
     │
     ▼
[AI Intent Classifier & Hybrid Router]
     │
     ├── (Confidence ≥ 0.80) ────────────────────────────────────────────────────────┐
     │   Intent Router                                                               │
     │   │                                                                           │
     │   ▼                                                                           │
     │   [Controlled Analytics Views (Pre-tested SQL / CTEs)]                        │
     │                                                                               │
     └── (Confidence < 0.80 or Dynamic Query) ──────────────────────────────┐        │
         Text-to-SQL Engine (Gemini 2.5 Flash + Semantic Context)           │        │
         │                                                                  │        │
         ▼                                                                  │        │
         [AST SQL Validator (sqlglot)]                                      │        │
           • Exactly 1 statement, SELECT/UNION only                         │        │
           • Function & Schema denylist (pg_sleep, pg_catalog, etc.)        │        │
           • Analytical table allow-list (rejects ai_audit_log)             │        │
           • Rejects Cartesian & Fan-Out joins                              │        │
           • Strips comments & enforces LIMIT <= 500                        │        │
           ├── VIOLATION ──► Self-Correction Loop (Max 2 retries)           │        │
           └── PASS ──────────────────────────────────────────────┐         │        │
                                                                  ▼         ▼        ▼
                                          [PostgreSQL 15+: Read-Only Role (`insightforge_ro`)]
                                            • statement_timeout = '5s'
                                            • REVOKE SELECT on `ai_audit_log`
                                                                  │
                                                                  ▼
                                                   [Structured Query Evidence / Rows]
                                                                  │
                                                                  ▼
                                           [Grounding Verifier (`verify_numeric_grounding`)]
                                             • Extracts numbers from LLM answer/explanation
                                             • Checks against evidence rows within ±0.05 or ±1.5%
                                             ├── PASS ──► grounding_verified = True
                                             └── FAIL ──► Reject Hallucination / Fallback
                                                                  │
                                                                  ▼
                                           [AIAuditService] ──► Records to `ai_audit_log`
```

---

## 🗂 Dataset-Aware Workspace (one active dataset for the whole app)

Choose the active dataset in the header switcher. With the **Olist demo** every page is unchanged (verified
byte-for-byte by `scripts/diff_olist_snapshots.py`); with an **uploaded dataset** every sidebar page shows that
dataset's data. All of it is deterministic (no LLM), owner-token protected, and runs through the same scoped
read-only, AST-validated query path. Full details: [docs/dataset_workspace_pages.md](docs/dataset_workspace_pages.md).

### What works for uploaded datasets

| Page | Uploaded dataset behaviour |
|---|---|
| Sidebar | Core pages + one page per table + Geography / Payments / Delivery / Sellers only when matching columns exist |
| Overview | KPI cards per measure, monthly trend, up to 8 breakdowns that reconcile to the total |
| Analytics | Any measure, daily / weekly / monthly trend, breakdowns |
| Table pages | Row count, column profile, KPIs, trend, breakdowns per table |
| Geography / Payments / Delivery / Sellers | Breakdowns by the matching columns (cross-table only along confirmed N:1 relationships) |
| Data Quality | Live checks: keys, FK orphans, negative values, future dates, missing values, join safety |
| Anomalies | MAD z-score, STL, IQR slices, IsolationForest with the Olist severity calibration; generic known-event candidates |
| Customers / Products | Olist-only pages (explained; use the table pages) |
| Anomalies → **Explain** | Root-cause waterfall: which groups drove the spike/drop, volume vs value ([docs/anomaly_explain.md](docs/anomaly_explain.md)) |
| **Forecast** | Baseline ETS forecast, 80% / 95% bands, backtest vs naive, refuses noisy series ([docs/forecasting.md](docs/forecasting.md)) |
| **Report** | One-click report (summary, KPIs, trend, breakdowns, anomaly drivers, forecast, data quality) with PDF download ([docs/report.md](docs/report.md)) |

### 📈 Forecast: click-path (works for the Olist demo and uploaded datasets)

1. Pick a dataset in the header switcher (e.g. **Olist demo**).
2. Sidebar → **Forecast** (below Anomalies).
3. Choose a **metric** (SUM / COUNT measures only), a **horizon** (1-6 months, default 3) and optionally tick
   **Exclude flagged anomaly days**.
4. Read the **reliability badge** (Good / Fair / Weak), **backtest MAPE vs naive**, the model and training window,
   the chart (actuals, dashed forecast, 80% and lighter 95% bands) and the lower / expected / upper table.
5. Noisy or short series are **refused with a reason** instead of showing numbers.

API: `GET /api/forecast?metric=&horizon=&exclude_anomalies=` and
`GET /api/datasets/{id}/forecast?...` (header `X-Owner-Token`).

### 🧾 Three deterministic features in plain words

- **Explain this anomaly.** Click **Explain** on any anomaly row. A waterfall shows which groups (category, state,
  seller, payment type, or your dataset's own columns) added or removed how much, from the expected value to what
  actually happened. A volume-vs-value card says whether it was more orders or bigger orders.
- **Forecast.** A cautious 1–6 month baseline with 80% / 95% bands. It tests itself on the last 3 months, labels its
  reliability, and refuses noisy or short series instead of guessing.
- **Report.** Sidebar → **Report**, or **Generate report** on Overview or after an upload, gives a one-click summary
  of everything above. It's shown on screen and as an A4 PDF, and its numbers are identical to the other pages.

No AI writes any number or sentence in these features. Viva questions and answers:
[docs/viva_preparation.md](docs/viva_preparation.md) (sections 8–10).

---

## 🚀 How to Run the Application

### 1. Backend Setup (FastAPI & PostgreSQL)

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Create environment configuration `.env`:
```env
# Database Settings (Read-Write)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=insightforge
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=insightforge

# Read-Only Database Role (Level 1 Security)
DB_RO_USER=insightforge_ro
DB_RO_PASSWORD=insightforge_ro_pass

# Rule 5: NO silent fake data (Set to 1 for demo/test mode without PostgreSQL)
USE_FIXTURES=0

# AI Configuration (Google Gemini API)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# API Rate Limiting
RATE_LIMIT_AI_ASK=30/minute
```

Provision Database, Schema, Views, and Read-Only Role:
```bash
psql -h localhost -U postgres -d insightforge -v ON_ERROR_STOP=1 -f database/schema.sql
psql -h localhost -U postgres -d insightforge -v ON_ERROR_STOP=1 -f database/views.sql
psql -h localhost -U postgres -d insightforge -v ON_ERROR_STOP=1 -f database/migrations/001_create_datasets_metadata.sql
psql -h localhost -U postgres -d insightforge -v ON_ERROR_STOP=1 -f database/migrations/002_create_dataset_semantic.sql
psql -h localhost -U postgres -d insightforge -v ON_ERROR_STOP=1 -f database/roles.sql   # run LAST: locks admin tables away from insightforge_ro
python database/seed.py
```

Launch FastAPI Uvicorn Server:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Live Health Check**: `http://localhost:8000/api/health`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **AI Query History**: `http://localhost:8000/api/ai/history?limit=50`

---

### 2. Multi-Container Deployment (Docker Compose)

Run the full stack (PostgreSQL + FastAPI + React UI) in isolated containers:
```bash
docker compose up --build
```
- **React Frontend**: `http://localhost:3000`
- **FastAPI Backend**: `http://localhost:8000`
- **PostgreSQL**: `localhost:5432`

---

### 3. Frontend Setup (React + Vite + Tailwind)

Navigate to `frontend/` directory and install dependencies:
```bash
cd frontend
npm install
npm run dev
```
- **Dashboard UI**: `http://localhost:3000/`

---

### 4. Automated Test Suites & Evaluations (Viva Checklist)

InsightForge includes isolated verification suites with clearly defined execution modes:

```bash
# 1. Deterministic Unit Tests (277 tests, runs offline with USE_FIXTURES=1)
python -m unittest discover -s backend/tests

# 2. Mathematical Analytical Invariants Test Suite (8 tests)
python database/test_analytics.py

# 3. Live Database Integration Tests (25 tests; requires real seeded PostgreSQL; skips if unseeded)
python -m unittest discover -s backend/tests_integration

# 4. AI Evaluation Benchmark
python backend/evals/run_eval.py --mode heuristic          # Canonical benchmark (83 intent test cases)
python backend/evals/run_eval.py --mode heuristic --live   # Evaluates evidence against live PostgreSQL
python backend/evals/run_eval.py --mode sql                # Evaluates dynamic Text-to-SQL against live PostgreSQL & Gemini API (30 cases)

# 5. Level 6 Generality Evaluation (Multi-dataset benchmark on 3 domains)
python backend/evals/dataset_eval.py --limit 5

# 6. Frontend TypeScript Validation & Production Build
cd frontend; npx tsc --noEmit; npm run build
```

---

## 📊 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | System health status, data source (`postgres` \| `fixture`), and database connectivity |
| `/api/kpis` | `GET` | Canonical executive KPIs (`Product Rev: R$ 13.22M`, `Gross Rev: R$ 15.42M`, `Orders: 96,478`, `AOV: R$ 159.83`, `CSAT: 4.16`) |
| `/api/analytics/revenue-trend` | `GET` | Monthly revenue, order volume, AOV, and MoM growth rates |
| `/api/analytics/categories` | `GET` | Top product category sales, unit volume, review scores, and revenue share % |
| `/api/analytics/states` | `GET` | Geographic customer state revenue distribution and active purchasing customers |
| `/api/analytics/sellers` | `GET` | Top merchant fulfillment performance, revenue, and product counts |
| `/api/analytics/payments` | `GET` | Payment method breakdown (credit card, boleto, voucher, debit card) and installment averages |
| `/api/analytics/delivery` | `GET` | Fulfillment SLA performance (`On-Time: 91.90%`, `Delayed: 8.10%`) and average delivery days |
| `/api/data-quality` | `GET` | Automated 10-check data quality audit findings, null counts, and join safety status |
| `/api/anomalies` | `GET` | Retrieve time series with flagged statistical anomalies (MAD Z-Score, STL, IQR, IsolationForest) |
| `/api/anomalies/scan` | `POST` | Trigger multi-metric deterministic anomaly scan (rate-limited, logged to audit log) |
| `/api/ai/ask` | `POST` | Controlled intent-based query: classify intent, fetch PostgreSQL evidence, verify grounding, and return insight |
| `/api/ai/sql-ask` | `POST` | Guarded Text-to-SQL: AST validator, readonly execution, self-correction, grounding verifier, and chart suggestions |
| `/api/ai/history` | `GET` | Retrieve recorded AI interaction audit history with latency, intent, route, and status |
| `/api/voice/transcribe` | `POST` | Level 4 Voice transcription endpoint (multipart audio, Gemini audio transcription, zero persistence) |
| `/api/datasets/upload` | `POST` | Level 5 Upload 1-5 CSV/TSV/XLSX files into isolated `ds_<8hex>` schema with profiling |
| `/api/datasets` | `GET` | Level 5 List uploaded datasets with summary, table counts, and row counts |
| `/api/datasets/{id}` | `GET` | Level 5 Get dataset profile, columns, data quality findings, and inferred relationships |
| `/api/datasets/{id}/preview` | `GET` | Level 5 Row preview (max 50 rows) for specified table |
| `/api/datasets/{id}` | `DELETE` | Level 5 Drop isolated schema `ds_<8hex>` and delete dataset metadata |
| `/api/datasets/{id}/semantic/generate` | `POST` | Level 6 Deterministic draft generation of measures, dimensions, and starter questions |
| `/api/datasets/{id}/semantic` | `GET` / `PATCH` | Level 6 Retrieve and confirm/edit dataset semantic modeling layer |
| `/api/datasets/{id}/ask` | `POST` | Level 6 Scoped Text-to-SQL asking engine with AST validation, privacy modes, and 1:N fan-out rejection |
| `/api/datasets/{id}/insights` | `GET` | Level 6 Pre-computed time-trend, top-N, and distribution queries plus rolling MAD anomaly detection |

---

## 🧠 Semantic Layer & Technical Architecture Specifications

- [`semantic/business_glossary.yaml`](semantic/business_glossary.yaml) — Standardized Business Terms & Synonyms
- [`semantic/metrics.yaml`](semantic/metrics.yaml) — Canonical Metric Formulas & Benchmark Targets
- [`semantic/dimensions.yaml`](semantic/dimensions.yaml) — Analytical Dimensions Catalog
- [`semantic/relationships.yaml`](semantic/relationships.yaml) — Join Graph & Fan-Out Multiplication Guardrails
- [`docs/viva_preparation.md`](docs/viva_preparation.md) — Comprehensive Viva Presentation & Defense Guide
- [`docs/dataset_qa.md`](docs/dataset_qa.md) — Level 6 Dataset-Aware Q&A, Semantic Layer & Scoped Text-to-SQL Architecture
- [`docs/text_to_sql.md`](docs/text_to_sql.md) — Level 3 Guarded Text-to-SQL Architecture, AST Validator Rules & Self-Correction
- [`docs/anomaly_detection.md`](docs/anomaly_detection.md) — Deterministic Multi-Method Anomaly Detection Engine Guide
- [`docs/ai_infrastructure.md`](docs/ai_infrastructure.md) — AI Infrastructure, Role Separation & Grounding Verifier Architecture

---

## 📄 License & Credits

Developed by **Rajeev Karakoti**, **Priyanshu Saklani**, **Prasanna Godiyal** for the B.Tech Major Project.  
Powered by PostgreSQL 15+, FastAPI, React 18, TailwindCSS, and Google Gemini API.
