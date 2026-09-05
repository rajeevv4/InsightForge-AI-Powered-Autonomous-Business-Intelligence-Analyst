# InsightForge — System Architecture Reference

**InsightForge** is an AI-Powered Autonomous Business Intelligence Analyst designed to bridge the gap between complex relational databases and non-technical decision-makers.

---

## High-Level System Layers

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        CLIENT / FRONTEND LAYER                         │
 │        React Chat UI  •  Interactive Plotly Charts  •  Report Viewer    │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ Natural Language Questions & Actions
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      LANGGRAPH MULTI-AGENT CORE                        │
 │  Schema Agent • SQL Agent • Analytics Agent • Root-Cause Agent         │
 │                  Visualization Agent • Report Agent                    │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ Standardized Data & Tool Calls
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         MCP TOOL LAYER                                 │
 │     db-mcp-server • stats-mcp-server • chart-mcp-server • semantic    │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ Guarded Read-Only Queries
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                     DATA & KNOWLEDGE LAYER                             │
 │    PostgreSQL (InsightForge Relational DB)  •  pgvector (RAG Semantic)  │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 Scope (Current Milestone: 25–30% Mid-Viva Target)

The primary goal of Phase 1 is establishing the **Real Data Foundation** using the **Olist Brazilian E-Commerce Dataset** inside PostgreSQL:

- **Relational Schema**: 7 core BI tables (`customers`, `products`, `sellers`, `orders`, `order_items`, `order_payments`, `order_reviews`).
- **ETL Pipeline**: Data cleaning, translation of Portuguese product categories to English, type enforcement, timestamp normalization, and bulk loading.
- **Analytical Views**: Pre-aggregated views for monthly sales, top categories, state revenue distribution, and delivery SLA performance.
- **Integrity Validation**: Automated verification script checking data types, foreign keys, row counts, and baseline revenue metrics.

---

## System Roadmap

| Phase | Milestone | Core Deliverables |
|---|---|---|
| **Phase 1** | **Database & Data Layer (Current - 25–30%)** | Clean PostgreSQL database, Olist ETL script, schema DDL, analytical views, verification suite. |
| **Phase 2** | **MCP Layer & Text-to-SQL (50%)** | Read-only MCP Database Server, Schema RAG with pgvector, Text-to-SQL with error self-correction. |
| **Phase 3** | **Multi-Agent Orchestration (75%)** | Stateful LangGraph workflow, Analytics Agent (anomaly detection), Root-Cause Agent (contribution decomposition). |
| **Phase 4** | **Full Platform & PDF Reports (100%)** | React UI with Plotly charts, ReportLab PDF report generation, benchmarking evaluation suite. |
