# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Target Milestone**: Phase 1, 2 & 3 — Real Data, Database Foundation, Analytics Suite & FastAPI REST API Layer (25–30% Mid-Viva Scope)

---

## 📌 Executive Summary

**InsightForge** transforms natural-language business queries into data-backed insights, visualizations, root-cause explanations, and executive recommendations.

This repository implements **Step 1 (Database Foundation)**, **Step 2 (Data Quality & Analytics Engine)**, and **Step 3 (FastAPI REST API Layer)** using the **Olist Brazilian E-Commerce Public Dataset** inside **PostgreSQL 16**.

---

## 📁 Project Architecture & Directory Structure

```
InsightForge/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point & CORS configuration
│   │   ├── config.py            # Environment configuration
│   │   ├── database.py          # PostgreSQL session dependency
│   │   ├── schemas/             # Pydantic API response models
│   │   ├── services/            # Service layer calling database analytics
│   │   └── routers/             # Modular REST endpoint routers
│   └── tests/
│       └── test_api.py          # Automated FastAPI test suite (9 tests)
├── database/
│   ├── schema.sql            # Table DDL, constraints, primary & foreign keys, indexes
│   ├── views.sql             # Analytical BI summary views & MoM window functions
│   ├── seed.py               # Python script to clean raw CSVs & bulk load into PostgreSQL
│   ├── verify_db.py          # Database integrity verification script
│   ├── data_quality.py       # Comprehensive 10-point Data Quality Audit module
│   ├── analytics.py          # Business Analytics & MoM Comparison Engine
│   └── test_analytics.py     # Automated Analytics Unit & Integration Test Suite
├── docs/
│   ├── backend_api.md           # [NEW] Complete REST API Documentation & OpenAPI reference
│   ├── architecture.md       # High-level system architecture summary
│   └── database_schema.md    # Data dictionary, metric formulas & quality rules
├── README.md                 # Complete setup, ETL processing, and execution guide
├── requirements.txt          # Python dependencies
└── .env.example              # PostgreSQL environment configuration template
```

---

## 🚀 How to Run the FastAPI Server

### Step 1: Install Dependencies & Setup Environment
```bash
pip install -r requirements.txt
cp .env.example .env
```

### Step 2: Seed PostgreSQL Database
```bash
python database/seed.py
```

### Step 3: Launch FastAPI Server
Run Uvicorn server:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Live API Endpoint**: `http://localhost:8000/api/health`
- **Interactive Swagger Documentation**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`

### Step 4: Run Automated Test Suites
Run database & analytics test suite:
```bash
python database/test_analytics.py
```
Run backend API test suite:
```bash
python backend/tests/test_api.py
```

---

## 📊 REST API Endpoints

| Endpoint | Method | Response Description |
|---|---|---|
| `/api/health` | `GET` | Health status, PostgreSQL connectivity, application name, version |
| `/api/kpis` | `GET` | Canonical business metrics (`Product Rev: 13.22M`, `Gross Rev: 15.42M`, `Orders: 96,478`, `AOV: 159.83`, `CSAT: 4.16`) |
| `/api/analytics/revenue-trend` | `GET` | Monthly sales trend, order volume, AOV, and MoM growth rates |
| `/api/analytics/categories` | `GET` | Product category sales, unit volume, CSAT, and revenue share % |
| `/api/analytics/states` | `GET` | Regional customer state sales distribution, active customers, state share % |
| `/api/analytics/sellers` | `GET` | Top merchant performance (volume, sales revenue, product count, CSAT) |
| `/api/analytics/payments` | `GET` | Payment method distribution (credit card, boleto, voucher, debit card) and installments |
| `/api/analytics/delivery` | `GET` | Fulfillment SLA breakdown (`On-Time`, `Delayed`, `Undelivered`) and delay days |
| `/api/data-quality` | `GET` | Automated 10-check data quality audit findings and join safety status |
