# Dataset-Aware Question & Answering (Level 6)

InsightForge Level 6 extends autonomous business intelligence beyond the fixed Olist schema to arbitrary user-uploaded CSV, TSV, and XLSX datasets with multi-file relational support, strict privacy enforcement, and schema-scoped SQL validation.

---

## 1. Architecture Overview

When a user uploads tabular datasets, InsightForge provisions an isolated PostgreSQL schema `ds_<8hex>` where tables are ingested via `psycopg2.sql.Identifier` quoted COPY. Level 6 enables conversational Text-to-SQL and automated exploratory data analysis over these custom datasets without compromising system security, database integrity, or user privacy.

```
┌─────────────────────────────────────────────────────────────┐
│                       Frontend UI                           │
│  - Dataset Switcher ("Asking: <name>")                      │
│  - Privacy Badge: "AI sees: schema only" vs "schema + data" │
│  - Starter Question Chips & Show SQL Inspection             │
│  - Quick Insights & Anomalies Visualization                 │
└──────────────────────────────┬──────────────────────────────┘
                               │
                HTTP REST (Owner Token Guarded)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend Router                   │
│  - POST /api/datasets/{id}/semantic/generate                │
│  - GET/PATCH /api/datasets/{id}/semantic                    │
│  - POST /api/datasets/{id}/ask (Rate-limited, quota safe)   │
│  - GET /api/datasets/{id}/insights (3 templates + MAD)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       ▼                                               ▼
┌──────────────────────────────┐       ┌──────────────────────────────┐
│     SQLValidator (AST)       │       │       Privacy Engine         │
│ - Schema-qualified names only│       │ - share_samples=False:       │
│ - Scoped to dataset tables   │       │   Schema only sent to LLM;   │
│ - Deny insightforge metadata │       │   Zero data rows sent to AI. │
│ - Generic 1:N fan-out guard  │       │ - share_samples=True:        │
│ - Forced LIMIT <= 500        │       │   Grounded LLM explanations  │
└──────────────────────────────┘       └──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  PostgreSQL Isolated Engine                 │
│  - Executed via read-only role insightforge_ro              │
│  - SET LOCAL search_path = "ds_<8hex>"                      │
│  - Statement timeout = 5s                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Deterministic Semantic Modeling Layer

The semantic layer is stored in `insightforge.dataset_semantic` (admin-only, strictly inaccessible to the read-only role `insightforge_ro`).

1. **Deterministic Draft Generation (`POST /api/datasets/{id}/semantic/generate`)**:
   - Inspects dataset profile column roles:
     - Measures: `FLOAT`, `INTEGER`, `NUMERIC` columns (excluding primary/foreign keys).
     - Dimensions: `TEXT`, categorical codes, and low-cardinality attributes.
     - Time Columns: `DATE`, `TIMESTAMP` columns.
     - Relationships & Candidate Keys: foreign key containment $\ge 95\%$.
   - Enriches synonyms, business descriptions, and generated starter questions deterministically or schema-only via Gemini.
   - Cells or data rows are **never** passed during generation unless `share_samples=True`.
2. **Review & Confirmation (`GET` & `PATCH /api/datasets/{id}/semantic`)**:
   - Dataset owners can review measures, default aggregations (`sum`, `avg`, `count`, `min`, `max`), format hints (`currency`, `number`, `percentage`), and starter questions.
   - Status transitions from `draft` to `confirmed`.

---

## 3. Scoped AST SQL Validation & Safety Guards

All generated SQL queries undergo rigorous AST parsing with `sqlglot` configured with `DatasetSQLContext`:
- **Explicit Schema Qualification**: All table references must match `{schema_name}.{table_name}`. Unqualified tables are rejected with actionable feedback to the correction loop.
- **Cross-Schema Isolation**: Access to other `ds_*` schemas, `public` tables, or `insightforge` metadata tables (`datasets`, `dataset_semantic`, `ai_audit_log`) is strictly blocked.
- **Single SELECT Only**: DDL (`CREATE`, `DROP`, `ALTER`), DML (`INSERT`, `UPDATE`, `DELETE`), multi-statement injection, and administrative functions (`pg_sleep`, `pg_terminate_backend`) are prohibited.
- **Generic 1:N Fan-Out Prevention**:
  - Automatically identifies joins between 1:N related tables (e.g., `customers` joined to `orders`).
  - Prohibits aggregating measures belonging to the "1" side without pre-aggregation in a Common Table Expression (CTE) or subquery.
- **Enforced Execution Limits**: Queries are bounded with `LIMIT <= 500` and executed with a 5-second statement timeout under the read-only user `insightforge_ro`.

---

## 4. Privacy Model & Zero-Sample Security

User data confidentiality is enforced at the core protocol level:

| Feature | `share_samples = False` (Default) | `share_samples = True` |
|---|---|---|
| **Prompt Contents** | Schema names, column types, and semantic metadata only. | Schema metadata + up to 3 sanitized sample values. |
| **Data Rows to LLM** | **ZERO data rows**. Returned SQL results are never sent to AI. | Returned SQL summary rows sent to LLM for grounded narrative. |
| **Summary Generation** | Deterministic Python template: `"Query returned N rows. Key findings: ..."` | Grounded Gemini explanation verified against returned numbers. |
| **Frontend Badge** | Amber badge: `AI sees: schema only` | Blue badge: `AI sees: schema + data` |

---

## 5. Starter Questions & Quick Insights

For every custom dataset, InsightForge immediately surfaces actionable starting points without requiring prompt engineering:
1. **Deterministic Starter Questions**: 6 to 8 tailored business questions (e.g., *"What is the total order amount across all records?"*, *"Top 5 categories by revenue"*, *"Count of records by status"*).
2. **Pre-computed Quick Insights (`GET /api/datasets/{id}/insights`)**:
   - **Time Trend**: Aggregated monthly or daily metric progression over time.
   - **Top-N Breakdown**: Top 5 ranking of key measures segmented by primary dimension.
   - **Distribution**: Category contribution and record frequency.
   - **Rolling Anomaly Scan**: Generic rolling Median Absolute Deviation (MAD) robust z-score detection on any daily series with $\ge 30$ continuous data points.
   - Results are cached in-memory with dataset-scoped cache keys `(dataset_id, "insights")`.

---

## 6. Audit Logging & Rate Limiting

- **Audit Trail**: Every query executed against a custom dataset is logged to `insightforge.ai_audit_log` with `dataset_id`, question text, generated SQL, latency, route, and success flag. Data values and returned rows are strictly omitted from logs.
- **Quota Protection**: Endpoints are rate-limited via `slowapi` (`settings.RATE_LIMIT_AI_ASK`). When Gemini free-tier quota limits are reached, the system catches HTTP 429 and responds with a clear `"AI quota reached"` notification without crashing the application.
