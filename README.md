# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Target Milestone**: Phase 1 & Phase 2 — Real Data, PostgreSQL Database Foundation & Business Analytics Suite (25–30% Mid-Viva Scope)

---

## 📌 Executive Summary

**InsightForge** transforms natural-language business queries into data-backed insights, visualizations, root-cause explanations, and executive recommendations.

This repository implements **Step 1 (Relational Database Foundation)** & **Step 2 (Data Quality & Business Analytics Foundation)** using the **Olist Brazilian E-Commerce Public Dataset** inside **PostgreSQL 16**.

---

## 📁 Project Architecture & Directory Structure

```
InsightForge/
├── data/
│   ├── raw/                  # Downloaded raw Olist CSV files
│   ├── processed/            # Cleaned/transformed CSV files
│   └── scenarios/            # Diagnostic benchmark test scenarios
├── database/
│   ├── schema.sql            # Table DDL, constraints, primary & foreign keys, indexes
│   ├── views.sql             # Analytical BI summary views & MoM window functions
│   ├── seed.py               # Python script to clean raw CSVs & bulk load into PostgreSQL
│   ├── verify_db.py          # Basic database health check script
│   ├── data_quality.py       # [NEW] Comprehensive 10-point Data Quality Audit module
│   ├── analytics.py          # [NEW] Business Analytics & MoM Comparison Engine
│   └── test_analytics.py     # [NEW] Automated Analytics Unit & Integration Test Suite
├── backend/                  # Reserved for FastAPI, LangGraph & MCP server (Phase 3+)
├── frontend/                 # Reserved for React dashboard (Phase 3+)
├── docs/
│   ├── architecture.md       # High-level system architecture summary
│   └── database_schema.md    # [UPDATED] Data dictionary, metric formulas & quality rules
├── README.md                 # Complete setup, ETL processing, and execution guide
├── requirements.txt          # Python dependencies
└── .env.example              # PostgreSQL environment configuration template
```

---

## 🛠️ Step-by-Step Execution Guide

### Step 1: Install Python Dependencies & Configure Database
```bash
pip install -r requirements.txt
cp .env.example .env
```
Ensure your `.env` matches your local PostgreSQL credentials (`localhost:5432`, DB `insightforge`).

### Step 2: Seed PostgreSQL Database (ETL Pipeline)
Place raw Olist CSVs in `data/raw/` and execute:
```bash
python database/seed.py
```

### Step 3: Run Data Quality Audit Profiler
Execute the automated 10-check data quality auditor:
```bash
python database/data_quality.py
```
*Evaluates row counts, missing value %, primary key uniqueness, foreign key integrity, domain value bounds, order status distributions, timestamp chronology, and fan-out join multiplier safety.*

### Step 4: Run Executive Business Analytics Engine
Execute the analytical query engine:
```bash
python database/analytics.py
```
*Prints Executive Summary KPIs, Top Categories & Revenue Share %, Top State Regional Contributions, Delivery SLA performance, and Payment Type distributions.*

### Step 5: Run Automated Analytics Test Suite
Execute the unit and integration test suite:
```bash
python database/test_analytics.py
```
*Verifies mathematical correctness, AOV accuracy, contribution percentage totals (100%), non-negative bounds, and zero join fan-out distortion.*

---

## 📊 Canonical Business Metric Definitions

- **Product Revenue**: `SUM(order_items.price)` for delivered orders (**`R$ 13,221,498.11`**).
- **Freight Revenue**: `SUM(order_items.freight_value)` for delivered orders (**`R$ 2,198,275.64`**).
- **Gross Revenue**: `SUM(price + freight_value)` for delivered orders (**`R$ 15,419,773.75`**).
- **Delivered Orders**: Total delivered e-commerce orders (**`96,478`**).
- **Units Sold**: Total items purchased across delivered orders (**`110,197`**).
- **Average Order Value (AOV)**: `Gross Revenue / Total Delivered Orders` (**`R$ 159.83`**).
- **Customer Satisfaction (CSAT)**: Mean review rating (**`4.16 / 5.0`**).
- **On-Time Delivery SLA**: `% of orders delivered on or before estimated date` (**`91.88%`**).

*Note: All line-item revenue metrics strictly enforce fan-out join multiplication protection to eliminate revenue duplication from multi-review or multi-payment orders.*
