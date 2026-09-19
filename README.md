# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Author & Lead Developer**: **Rajeev Karakoti**  
> **Status**: Verified Steps 1–7 Complete (Mid-Viva Ready Scope)

---

## 📌 Executive Summary

**InsightForge** is an AI-powered, autonomous Business Intelligence platform designed and developed by **Rajeev Karakoti**. It transforms natural-language business questions into data-backed executive insights, interactive visualizations, zero-hallucination grounded explanations, and data quality audits.

Built on top of the **Olist Brazilian E-Commerce Dataset** inside **PostgreSQL 16**, InsightForge uses a strict separation between AI reasoning and database analytics: the LLM never generates arbitrary SQL or accesses PostgreSQL directly; all numerical results are produced by pre-validated PostgreSQL analytics functions.

---

## 👤 Author & Project Credits

- **Developer & Architect**: **Rajeev Karakoti**
- **Project Type**: B.Tech Major Project — Autonomous BI & AI Analytics System
- **Dataset**: Olist Brazilian E-Commerce Dataset (~100,000 orders, 9 core tables)
- **Repository**: [InsightForge-AI-Powered-Autonomous-Business-Intelligence-Analyst](https://github.com/rajeevv4/InsightForge-AI-Powered-Autonomous-Business-Intelligence-Analyst)

---

## 🏗 System Architecture & Directory Structure

```
InsightForge/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI application entry point & router inclusion
│   │   ├── config.py                 # Environment configuration (DB & Gemini settings)
│   │   ├── database.py               # SQLAlchemy PostgreSQL connection pooling
│   │   ├── schemas/                  # Pydantic request & response validation schemas
│   │   │   └── ai.py                 # AskAIRequest & AskAIResponse models
│   │   ├── services/                 # Business logic service layer
│   │   │   ├── analytics_service.py  # Trusted analytics functions
│   │   │   ├── data_quality_service.py # Data quality audit engine
│   │   │   ├── ai_analytics_router.py # Controlled intent router
│   │   │   └── ai_service.py         # Gemini classifier & grounded synthesizer
│   │   └── routers/                  # Modular REST API endpoints
│   │       ├── health.py             # Health check endpoint
│   │       ├── kpis.py               # Canonical KPI summary endpoint
│   │       ├── analytics.py          # Category, revenue, state, seller, delivery endpoints
│   │       ├── data_quality.py       # Data quality audit endpoint
│   │       └── ai.py                 # POST /api/ai/ask endpoint
│   └── tests/
│       ├── test_api.py               # REST API test suite (9 tests)
│       └── test_ai_api.py            # AI Service & endpoint test suite (8 tests)
├── database/
│   ├── schema.sql                    # PostgreSQL DDL schema & constraints
│   ├── views.sql                     # Analytical SQL summary views
│   ├── seed.py                       # Data cleaning & bulk CSV loader
│   ├── data_quality.py               # 10-check database audit script
│   ├── analytics.py                  # Analytics execution module
│   └── test_analytics.py             # Analytics unit test suite
├── frontend/                         # React + TypeScript + Tailwind BI Dashboard
│   ├── src/
│   │   ├── components/               # UI components & charts
│   │   │   ├── navigation/           # Sidebar & Header navigation shell
│   │   │   │   ├── Sidebar.tsx       # Responsive mobile drawer & sidebar
│   │   │   │   └── Header.tsx        # Page titles & PostgreSQL connection status
│   │   │   └── AskInsightForge.tsx   # Interactive AI Query Component
│   │   ├── layouts/
│   │   │   └── AppLayout.tsx         # Application shell layout wrapper
│   │   ├── pages/                    # Dedicated SaaS page routes
│   │   │   ├── OverviewPage.tsx      # Executive Overview & KPI grid
│   │   │   ├── AskPage.tsx           # Ask InsightForge AI page
│   │   │   ├── AnalyticsPage.tsx     # Categorized analytics & filter tabs
│   │   │   └── DataQualityPage.tsx   # Data Quality audit view
│   │   ├── services/
│   │   │   └── api.ts                # Axios HTTP client service
│   │   ├── types/
│   │   │   └── api.ts                # TypeScript API interfaces
│   │   └── App.tsx                   # React Router (v6) route definitions
├── semantic/                         # Business Glossary & Semantic Layer
│   ├── business_glossary.yaml        # 19 standardized business terms
│   ├── metrics.yaml                  # 8 canonical metric formulas & targets
│   ├── dimensions.yaml               # 9 analytical dimensions catalog
│   ├── relationships.yaml            # Join graph & fan-out safety rules
│   ├── validate_semantic_layer.py    # Semantic validation suite
│   └── test_semantic_layer.py        # Semantic unit tests
├── docs/                             # Technical Specifications & Documentation
│   ├── ai_integration.md             # AI integration architecture & grounding rules
│   ├── backend_api.md                # Complete REST API reference
│   ├── architecture.md               # System architecture breakdown
│   ├── database_schema.md            # Database schema dictionary & ETL rules
│   └── semantic_layer.md             # Semantic layer architecture guide
├── requirements.txt                  # Python dependencies
└── README.md                         # Project documentation
```

---

## 🤖 AI Capability — "Ask InsightForge"

InsightForge includes a grounded AI natural-language analyst interface powered by **Google Gemini 2.5 Flash**:

- **Natural-Language Business Queries**: Stakeholders can ask natural language questions like *"Which category generated the highest revenue?"*, *"What is our average order value?"*, *"Which state has the highest sales?"*, or *"How is our delivery performance?"*.
- **Allow-Listed Intent Classification**: Classifies questions into 8 supported intents (`kpi_summary`, `revenue_trend`, `category_analysis`, `state_analysis`, `seller_analysis`, `payment_analysis`, `delivery_analysis`, `data_quality`).
- **Controlled Analytics Router**: Intent maps directly to audited Python analytics functions. No arbitrary SQL is generated or executed by the LLM.
- **Evidence-Grounded Explanations**: Explanations are generated strictly from verified PostgreSQL evidence payloads.
- **Zero Hallucination Security**: The LLM cannot fabricate numerical values or access database credentials.

---

## 🚀 How to Run the Application

### 1. Backend Setup (FastAPI & PostgreSQL)

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Create environment configuration `.env`:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=insightforge
DB_USER=postgres
DB_PASSWORD=your_password
DB_SCHEMA=insightforge
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

Seed PostgreSQL database (run once):
```bash
python database/seed.py
```

Launch FastAPI Uvicorn Server:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Live Health Check**: `http://localhost:8000/api/health`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

### 2. Frontend Setup (React + Vite + Tailwind)

Navigate to frontend directory and install dependencies:
```bash
cd frontend
npm install
```

Launch Vite Development Server:
```bash
npm run dev
```
- **React Dashboard UI**: `http://localhost:3000/`

---

### 3. Run Automated Test Suites

Run database & analytics tests:
```bash
python database/test_analytics.py
```

Run backend API & AI integration tests:
```bash
python3 -m unittest discover -s backend/tests
```

Run semantic layer validation:
```bash
python3 semantic/validate_semantic_layer.py
python3 semantic/test_semantic_layer.py
```

Run frontend TypeScript typecheck & production build:
```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## 📊 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | System health status & PostgreSQL database connectivity |
| `/api/kpis` | `GET` | Canonical executive KPIs (`Product Rev: 13.22M`, `Gross Rev: 15.42M`, `Orders: 96,478`, `AOV: 159.83`, `CSAT: 4.16`) |
| `/api/analytics/revenue-trend` | `GET` | Monthly revenue, order volume, AOV, and MoM growth rates |
| `/api/analytics/categories` | `GET` | Top product category sales, unit volume, review scores, and revenue share % |
| `/api/analytics/states` | `GET` | Geographic customer state revenue distribution and active purchasing customers |
| `/api/analytics/sellers` | `GET` | Top merchant fulfillment performance, revenue, and product counts |
| `/api/analytics/payments` | `GET` | Payment method breakdown (credit card, boleto, voucher, debit card) and installment averages |
| `/api/analytics/delivery` | `GET` | Fulfillment SLA performance (`On-Time: 91.9%`, `Delayed: 8.1%`) and delivery days |
| `/api/data-quality` | `GET` | Automated 10-check data quality audit findings, null counts, and join safety status |
| `/api/ai/ask` | `POST` | Process natural language question, classify intent, fetch PostgreSQL evidence, and return grounded explanation |

---

## 🧠 Semantic Layer Specifications

- [`semantic/business_glossary.yaml`](file:///Users/rajeev/Major%20Project-%20InsightForge/semantic/business_glossary.yaml) — 19 Standardized Business Terms
- [`semantic/metrics.yaml`](file:///Users/rajeev/Major%20Project-%20InsightForge/semantic/metrics.yaml) — 8 Canonical Metric Formulas & Benchmark Targets
- [`semantic/dimensions.yaml`](file:///Users/rajeev/Major%20Project-%20InsightForge/semantic/dimensions.yaml) — 9 Analytical Dimensions Catalog
- [`semantic/relationships.yaml`](file:///Users/rajeev/Major%20Project-%20InsightForge/semantic/relationships.yaml) — Join Graph & Fan-Out Multiplication Guardrails
- [`docs/ai_integration.md`](file:///Users/rajeev/Major%20Project-%20InsightForge/docs/ai_integration.md) — AI Architecture & Grounding Specification
- [`docs/backend_api.md`](file:///Users/rajeev/Major%20Project-%20InsightForge/docs/backend_api.md) — Backend API Documentation

---

## 📄 License & Credits

Developed by **Rajeev Karakoti** for the B.Tech Major Project.  
Powered by PostgreSQL, FastAPI, React, TailwindCSS, and Google Gemini API.
