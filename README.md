# InsightForge — AI-Powered Autonomous Business Intelligence Analyst

> **B.Tech Major Project**  
> **Target Milestone**: Phase 1 — Real Data & PostgreSQL Database Foundation (25–30% Mid-Viva Scope)

---

## 📌 Executive Summary

**InsightForge** transforms natural-language business queries into data-backed insights, visualizations, root-cause explanations, and executive recommendations.

This repository implements **Step 1: Dataset and Database Foundation**, establishing a clean PostgreSQL database model using the **Olist Brazilian E-Commerce Public Dataset**.

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
│   ├── views.sql             # Analytical summary views (revenue, delivery SLA, top categories)
│   ├── seed.py               # Python script to clean raw CSVs & bulk load into PostgreSQL
│   └── verify_db.py          # Database health check and metric verification script
├── backend/                  # Reserved for FastAPI, LangGraph & MCP server (Phase 2+)
├── frontend/                 # Reserved for React dashboard (Phase 2+)
├── docs/
│   ├── architecture.md       # High-level architecture summary
│   └── database_schema.md    # Data dictionary & metric definitions
├── README.md                 # Complete setup, ETL processing, and database guide
├── requirements.txt          # Python dependencies
└── .env.example              # PostgreSQL environment configuration template
```

---

## 🗄️ Database Data Model (Olist Mapping)

The database schema (`insightforge`) comprises **7 core relational tables**:

```
                    ┌─────────────────────────┐
                    │        CUSTOMERS        │
                    ├─────────────────────────┤
                    │ PK: customer_id         │
                    │     customer_unique_id  │
                    │     city, state, zip    │
                    └────────────┬────────────┘
                                 │ 1
                                 │
                                 │ N
                    ┌────────────┴────────────┐
                    │         ORDERS          │
                    ├─────────────────────────┤
                    │ PK: order_id            │
                    │ FK: customer_id         │
                    │     order_status        │
                    │     purchase_timestamp  │
                    │     delivered_date, etc │
                    └──────┬─────┬─────┬──────┘
                           │1    │1    │1
                           │     │     │
                          N│    N│    N│
   ┌───────────────────────┴┐   │   ┌──┴──────────────────────┐
   │      ORDER_ITEMS       │   │   │     ORDER_PAYMENTS      │
   ├────────────────────────┤   │   ├─────────────────────────┤
   │ PK: order_id, item_id  │   │   │ PK: order_id, seq_num   │
   │ FK: order_id           │   │   │ FK: order_id            │
   │ FK: product_id ──┐     │   │   │     payment_type        │
   │ FK: seller_id ───┼─┐   │   │   │     payment_value       │
   └──────────────────┼─┼───┘   │   └─────────────────────────┘
                      │ │       │
                      │ │      N│
                      │ │   ┌───┴─────────────────────┐
                      │ │   │      ORDER_REVIEWS      │
                      │ │   ├─────────────────────────┤
                      │ │   │ PK: review_id, order_id │
                      │ │   │ FK: order_id            │
                      │ │   │     review_score (1-5)  │
                      │ │   │     comment_title, msg  │
                      │ │   └─────────────────────────┘
                      │ │
     ┌────────────────┴─┴──────────┐       ┌─────────────────────────┐
     │          PRODUCTS           │       │         SELLERS         │
     ├─────────────────────────────┤       ├─────────────────────────┤
     │ PK: product_id              │       │ PK: seller_id           │
     │     category_name           │       │     city, state, zip    │
     │     category_name_english   │       └─────────────────────────┘
     │     dimensions, weight      │
     └─────────────────────────────┘
```

### Table Overview
1. **`customers`**: Customer locations & unique tracking hashes across Brazilian states.
2. **`products`**: Product specifications, merged with English category translations (`product_category_name_english`).
3. **`sellers`**: Merchant directory and state/city locations.
4. **`orders`**: Fact header recording purchase, approval, carrier handoff, and delivery timestamps.
5. **`order_items`**: Line-item details linking orders to products & sellers with unit price and freight costs.
6. **`order_payments`**: Payment method splits (credit card, boleto, voucher, debit) and installments.
7. **`order_reviews`**: Customer review ratings (1 to 5) and feedback messages.

---

## 🛠️ Step-by-Step Setup & Execution Guide

### Step 1: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and configure your PostgreSQL database credentials:
```bash
cp .env.example .env
```
Edit `.env` if necessary:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=insightforge
DB_USER=postgres
DB_PASSWORD=your_password
DB_SCHEMA=insightforge
```

### Step 3: Place Raw Olist CSV Dataset Files
Place the following 8 Olist dataset CSV files inside the `data/raw/` folder:
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `product_category_name_translation.csv`
- `olist_sellers_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`

### Step 4: Run the ETL Cleaning & Seeding Script
Execute `database/seed.py`. This script automatically:
1. Connects to PostgreSQL.
2. Applies `database/schema.sql` (Creates schema, tables, constraints, and indexes).
3. Cleans nulls, normalizes date timestamps, and translates Portuguese product category names to English.
4. Bulk loads cleaned data into PostgreSQL in strict foreign-key order.
5. Applies `database/views.sql` (Creates analytical summary views).

```bash
python database/seed.py
```

### Step 5: Verify Database Health & Baseline Metrics
Execute `database/verify_db.py` to check row counts, analytical view statuses, and print baseline BI revenue metrics:
```bash
python database/verify_db.py
```

---

## 📊 Analytical Views Provided

- **`view_monthly_sales_performance`**: Monthly order volume, item counts, product revenue, freight revenue, and gross revenue.
- **`view_category_performance`**: Sales volume, total revenue, average item price, and average CSAT score per English product category.
- **`view_state_sales_performance`**: Sales volume and total revenue broken down by customer state.
- **`view_delivery_sla_performance`**: Actual delivery days vs estimated delivery days with SLA status (`On-Time`, `Delayed`, `Undelivered`).

---

## 🚀 Next Steps (Phase 2)
- Build read-only Model Context Protocol (MCP) Database Server.
- Create schema-grounded RAG semantic layer with `pgvector`.
- Develop stateful LangGraph multi-agent orchestration engine.
