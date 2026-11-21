# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Authors & Developers**: **Rajeev Karakoti**, **Priyanshu Saklani**, **Prasanna Godiyal**  
> **Status**: ✅ **Levels 0 & 1 Complete — Viva & Production Ready**  
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

Built on top of the **Olist Brazilian E-Commerce Dataset** inside **PostgreSQL 16**, InsightForge enforces a strict architectural boundary between AI reasoning and database analytics: the LLM never receives database credentials, never executes arbitrary SQL, and all numerical outputs are verified by a deterministic Grounding Verifier against computed PostgreSQL evidence before reaching the user.

---

## 🚀 Project Levels & Implementation Status

| Level | Focus Area | Status | Key Deliverables & Engineering Achievements |
|---|---|:---:|---|
| **Level 0** | **Correctness & Mathematical Soundness** | ✅ **COMPLETE** | • **Eliminated Join Fan-Out**: Order-level review CTE in `views.sql` ensures category contribution strictly sums to $100.00\%$ and product revenue equals canonical $R\$ 13,221,498.11$.<br>• **Real Data Quality Audits**: Replaced hardcoded strings with computed PK uniqueness, FK integrity, domain bounds, and join safety audits.<br>• **BRL Standard**: Unified currency symbol to $R\$$ throughout charts, KPI cards, and heuristic answers.<br>• **Robust Intent Routing**: Word-boundary regex matching prevents false positives on sub-words.<br>• **Engine Pooling**: Module-level pooled SQLAlchemy engine (`pool_pre_ping=True`). |
| **Level 1** | **Infrastructure for AI Features & Defense** | ✅ **COMPLETE** | • **Read-Only Database Role**: `insightforge_ro` role with SELECT-only grants and `statement_timeout = '5s'`.<br>• **AI Audit Logging**: `AIAuditService` persisting question, intent, latency, route, success flag, and error with `GET /api/ai/history`.<br>• **Golden Evaluation Suite**: 55 benchmark questions in `golden_questions.yaml` scored by offline CLI `run_eval.py` (**96.36% intent accuracy**, **100.00% numeric faithfulness**).<br>• **Grounding Verifier**: Regex token parser in `grounding.py` matching numbers against evidence within $\pm 0.05$ / $1.5\%$ with heuristic fallback.<br>• **API Rate Limiting**: `slowapi` limiter protecting `/api/ai/ask` (default 30/min).<br>• **Docker & CI/CD**: Multi-container `docker-compose.yml` and automated GitHub Actions CI workflow. |
| **Level 1.5** | **Removal of Silent Fixture Fallbacks & Truthful Health** | ✅ **COMPLETE** | • **Zero Silent Fake Data**: Eliminated automatic canonical fallbacks; services raise `DatabaseUnavailableError` unless `USE_FIXTURES=1`.<br>• **HTTP 503 Service Unavailable**: Endpoints return standard 503 `"Database unavailable"` when DB is down.<br>• **Truthful Health & Data Source**: `/api/health` returns `data_source: "postgres" \| "fixture"` and reports `database: "disconnected"` truthfully.<br>• **UI DEMO DATA Badge**: Header displays prominent amber `"DEMO DATA"` badge when operating on fixtures.<br>• **Frontend ErrorBanner**: UI displays `ErrorBanner` on 503s instead of empty/fabricated charts.<br>• **Dual-Mode Eval CLI**: `run_eval.py` supports `--mode heuristic` and `--mode gemini`. |

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
│   │   │   └── kpis.py               # KPISummaryResponse schema
│   │   ├── services/                 # Business logic service layer
│   │   │   ├── analytics_service.py  # Trusted analytics functions
│   │   │   ├── anomaly_service.py    # Deterministic anomaly detection (MAD, STL, IQR, IsolationForest)
│   │   │   ├── data_quality_service.py # 10-check data quality audit engine
│   │   │   ├── ai_analytics_router.py # Controlled intent-to-view router
│   │   │   ├── ai_service.py         # Gemini classifier & grounded synthesizer
│   │   │   ├── audit_service.py      # AI interaction audit logger
│   │   │   └── grounding.py          # Deterministic regex numeric faithfulness verifier
│   │   └── routers/                  # Modular REST API endpoints
│   │       ├── health.py             # Health check endpoint
│   │       ├── kpis.py               # Canonical KPI summary endpoint
│   │       ├── analytics.py          # Category, revenue, state, seller, delivery endpoints
│   │       ├── data_quality.py       # Data quality audit endpoint
│   │       ├── anomalies.py          # GET /api/anomalies & POST /api/anomalies/scan
│   │       └── ai.py                 # POST /api/ai/ask & GET /api/ai/history endpoints
│   ├── evals/
│   │   ├── golden_questions.yaml     # 63 structured evaluation test cases with canonical metrics
│   │   └── run_eval.py               # Offline benchmark scoring intent accuracy & numeric faithfulness
│   └── tests/                        # 45+ unit tests
│       ├── test_api.py               # Core REST API endpoint tests
│       ├── test_ai_api.py            # AI router, history, rate-limiting & fallback tests
│       ├── test_anomalies.py         # Multi-method anomaly detection & Black Friday tests
│       ├── test_grounding.py         # Grounding verifier & hallucination detection tests
│       ├── test_audit_service.py     # AI audit logging & ring-buffer tests
│       ├── test_fixture_guard.py     # Rule 5 fixture enforcement tests
│       └── test_database_unavailable.py # Level 1.5 DB down 503 and fixture badge tests
├── database/
│   ├── schema.sql                    # PostgreSQL DDL schema & table constraints
│   ├── views.sql                     # Analytical views with CTE fan-out prevention
│   ├── roles.sql                     # Read-only role (insightforge_ro) with 5s timeout
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
[AI Intent Classifier] ───(Gemini 2.5 Flash / Word-Boundary Regex)
     │
     ▼
[Controlled Analytics Router]
     │
     ▼
[PostgreSQL 16: Read-Only Role (`insightforge_ro`)]
  • statement_timeout = '5s'
  • SELECT on schema `insightforge` views only
     │
     ▼
[Structured Evidence Payload]
     │
     ▼
[Grounding Verifier (`verify_numeric_grounding`)]
  • Regex extracts every number from LLM answer
  • Checks against evidence within ±0.05 or ±1.5%
  ├── PASS ──► Return Verified Answer (grounding_verified=True)
  └── FAIL ──► Reject Hallucination ──► Return Heuristic Fallback
     │
     ▼
[AIAuditService] ──► Records question, route, latency, and status in `ai_audit_log`
```

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
psql -h localhost -U postgres -d insightforge -f database/schema.sql
psql -h localhost -U postgres -d insightforge -f database/views.sql
psql -h localhost -U postgres -d insightforge -f database/roles.sql
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

InsightForge includes 4 automated verification suites that can be executed before or during project presentations:

```bash
# 1. Database & Analytical Invariants Test Suite (8 tests)
python database/test_analytics.py

# 2. Backend API, AI Infrastructure & Fixture Guard Unit Tests (45+ tests)
python -m unittest discover -s backend/tests

# 3. AI Golden Question Evaluation Benchmark (63 test cases)
python backend/evals/run_eval.py

# 4. Frontend TypeScript Validation & Production Build
cd frontend; npx tsc --noEmit; npm run build
```

---

## 📊 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | System health status & PostgreSQL database connectivity |
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
| `/api/ai/ask` | `POST` | Process natural language question, classify intent, fetch PostgreSQL evidence, verify grounding, and return insight |
| `/api/ai/history` | `GET` | Retrieve recorded AI interaction audit history with latency, intent, and status |

---

## 🧠 Semantic Layer Specifications

- [`semantic/business_glossary.yaml`](semantic/business_glossary.yaml) — Standardized Business Terms & Synonyms
- [`semantic/metrics.yaml`](semantic/metrics.yaml) — Canonical Metric Formulas & Benchmark Targets
- [`semantic/dimensions.yaml`](semantic/dimensions.yaml) — Analytical Dimensions Catalog
- [`semantic/relationships.yaml`](semantic/relationships.yaml) — Join Graph & Fan-Out Multiplication Guardrails
- [`docs/viva_preparation.md`](docs/viva_preparation.md) — Comprehensive Viva Presentation & Defense Guide
- [`docs/ai_infrastructure.md`](docs/ai_infrastructure.md) — AI Infrastructure, Role Separation & Verifier Architecture
- [`docs/anomaly_detection.md`](docs/anomaly_detection.md) — Deterministic Multi-Method Anomaly Detection Engine Guide

---

## 📄 License & Credits

Developed by **Rajeev Karakoti**, **Priyanshu Saklani**, **Prasanna Godiyal** for the B.Tech Major Project.  
Powered by PostgreSQL 16, FastAPI, React 18, TailwindCSS, and Google Gemini API.
