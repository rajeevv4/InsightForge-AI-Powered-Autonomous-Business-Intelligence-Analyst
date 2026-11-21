# InsightForge — Level 5: Dataset Workspace Architecture & Reference

## 1. Executive Summary & Core Principles

Level 5 introduces the **Dataset Workspace**, enabling users to upload and profile any tabular dataset (CSV, TSV, XLSX) into an isolated PostgreSQL schema with deterministic zero-LLM profiling, rigorous schema boundaries, and privacy safeguards.

### Core Architecture Rules

* **Rule 10 (Dynamic Metadata — Never Assume Olist)**: All dataset workspace features operate strictly on dynamic metadata (`DatasetProfile`, `TableProfile`, `ColumnProfile`, `RelationshipProfile`), never hardcoding table, column, or metric names. The Brazilian e-commerce dataset is registered as a built-in read-only demo dataset (`olist-demo`, ID: `00000000-0000-0000-0000-000000000001`).
* **Rule 11 (Untrusted Data & Identifier Protection)**: Uploaded filenames, headers, and values are strictly untrusted. Identifiers are never interpolated into SQL via f-strings; instead, `psycopg2.sql.Identifier` is enforced. Raw cell values are never passed to LLM prompts unless the dataset owner explicitly enables `share_samples=True`.
* **Rule 12 (Schema Isolation & Least Privilege)**: Each dataset upload is provisioned into a private PostgreSQL schema named `ds_<8hex>`. Read-only analytics credentials (`insightforge_ro`) are granted `USAGE` and `SELECT` on the dataset schema, while administrative metadata tables in `insightforge` schema remain strictly forbidden (`REVOKE ALL`).

---

## 2. PostgreSQL Schema Isolation & Security Model

```
PostgreSQL Database
│
├── schema "insightforge" (Admin only, restricted from insightforge_ro)
│   ├── datasets (metadata, owner_token_hash, status, share_samples, expiry)
│   ├── dataset_tables (table metadata, candidate PK/time column, findings)
│   ├── dataset_columns (column stats, types, roles, user descriptions)
│   ├── dataset_relationships (inferred/confirmed FK pairs, cardinality)
│   ├── ai_audit_log (query audit logs)
│   └── [Olist Analytics Tables & Views]
│
├── schema "ds_a1b2c3d4" (Tenant A Upload - Isolated)
│   ├── GRANT USAGE, SELECT TO insightforge_ro;
│   ├── retail_customers (Table)
│   └── retail_orders (Table)
│
└── schema "ds_9f8e7d6c" (Tenant B Upload - Isolated)
    ├── GRANT USAGE, SELECT TO insightforge_ro;
    └── student_marks (Table)
```

### Privileges Matrix

| Target | Admin Role (`insightforge_admin`) | Read-Only Role (`insightforge_ro`) |
| :--- | :--- | :--- |
| `insightforge.datasets` | Full (SELECT, INSERT, UPDATE, DELETE) | **DENIED** (Throws `permission denied`) |
| `insightforge.dataset_*` | Full (SELECT, INSERT, UPDATE, DELETE) | **DENIED** (Throws `permission denied`) |
| `insightforge.ai_audit_log` | Full | **DENIED** |
| `insightforge.orders` (Olist) | Full | SELECT only |
| `ds_<8hex>.*` (Tenant tables) | Full (CREATE, DROP, COPY, SELECT) | SELECT only (via `search_path`) |

---

## 3. Storage, Quotas, and Bounds

To protect the shared PostgreSQL instance (Supabase free-tier 500 MB quota) and prevent denial-of-service:

| Parameter | Limit | Enforcement Mechanism |
| :--- | :--- | :--- |
| Max Upload Size | 25 MB per file | FastAPI streaming byte counter (HTTP 413) |
| Max Files per Upload | 1 to 5 tabular files | FastAPI validation (HTTP 400) |
| Max Rows per Table | 200,000 rows | Stream row parser (`DatasetFileParser`) |
| Max Columns per Table | 100 columns | Header validation (`DatasetFileParser`) |
| Max Datasets per Owner | 3 active datasets | Database quota check on `owner_token_hash` |
| Dataset Retention | 24 hours | Automatic cleanup script (`scripts/cleanup_datasets.py`) |
| Database Size Guard | 450 MB max database size | Pre-flight check via `pg_database_size()` (HTTP 507) |
| Upload Rate Limit | 5 uploads / hour | SlowAPI limiter on `POST /api/datasets` |

---

## 4. Deterministic Profiling Pipeline (Zero LLM)

Profiling executes immediately after PostgreSQL `COPY` ingestion without consuming LLM tokens:

1. **Identifier Sanitization (`dataset_sanitizer.py`)**:
   - Converts arbitrary headers into snake_case ASCII.
   - Strips SQL injection characters (`"`, `'`, `;`, `--`, `/*`).
   - Resolves collisions with PostgreSQL reserved keywords (`select` $\rightarrow$ `col_select`).
   - Prefixes leading digits (`123_rev` $\rightarrow$ `col_123_rev`).
   - Deduplicates identical headers (`category`, `category_1`, `category_2`).
   - Enforces PostgreSQL 63-character limit.

2. **File Content & Format Safety (`dataset_file_parser.py`)**:
   - Accepts `.csv`, `.tsv`, and `.xlsx`.
   - Rejects macro-enabled workbooks (`.xlsm` or zip archives containing `vbaProject.bin`).
   - Rejects disguised binary files (e.g. ELF, PE, PDF, PNG with `.csv` extension).
   - Detects character encodings (UTF-8, UTF-8 BOM, Latin-1).
   - Flags date format ambiguity (e.g., `05/06/2023` where both parts $\le 12$).

3. **Statistical Profile & Analytical Roles (`dataset_profiler.py`)**:
   - Computes null %, distinct values, min, max, mean, median, standard deviation.
   - Infers column roles:
     - `id`: Primary and foreign keys, UUIDs, unique integer codes.
     - `datetime`: Dates, timestamps, ISO-8601 strings.
     - `measure`: Continuous numeric metrics (amounts, revenues, quantities).
     - `dimension`: Low-cardinality categorical attributes (states, categories).
     - `boolean`: Flags and boolean indicators (`is_vip`, `passed`).
     - `free_text`: High-cardinality descriptive text (notes, reviews).

4. **Multi-Table Relationship Inference**:
   - Detects foreign key pairs across multi-file uploads using:
     - Name matching (`orders.customer_id` $\leftrightarrow$ `customers.customer_id`).
     - Value containment: $\ge 95\%$ of child column values present in parent column.
     - Cardinality determination: `1:1` if child values are unique, `1:N` otherwise.

5. **Automated Quality Findings**:
   - Identifies constant columns (100% same value).
   - Identifies high-null columns ($> 50\%$ null).
   - Identifies suspicious negative values in financial or quantity metrics.
   - Highlights ambiguous date representations.

---

## 5. Privacy & Sample Sharing Model

* **Default Privacy (`share_samples=False`)**:
  - `stats["top_5"]` values are completely omitted.
  - LLM prompts receive only column safe names, data types, analytical roles, and user descriptions.
  - Zero row or cell data is transmitted to Gemini or external APIs.
* **Opt-In Sample Sharing (`share_samples=True`)**:
  - Up to 5 representative values are extracted for categorical dimensions only.
  - Allows text-to-SQL synthesis to know exact categorical literals (e.g., Brazilian state codes `SP`, `RJ`).
  - Raw table cell dumps are never passed to the LLM.

---

## 6. Tenancy & Owner Token Authentication Analysis

### Owner Token Design (`X-Owner-Token`)
* Unauthenticated users are assigned a cryptographically random owner token (`own_<32hex>`).
* The token is stored in the browser's `localStorage` and passed in the `X-Owner-Token` HTTP header.
* Only the SHA-256 hash (`owner_token_hash`) is stored in PostgreSQL.
* Tenants can only list, view, edit, or delete datasets matching their `owner_token_hash`.

### Trade-Off Analysis: Owner Token vs. Full User Accounts

| Factor | Anonymous Owner Token (Current) | Full User Accounts (RBAC) |
| :--- | :--- | :--- |
| **User Friction** | Zero friction (instant upload without signup) | High friction (requires login/OAuth) |
| **Cross-Device Persistence** | Browser-scoped (lost if cache cleared) | Persistent across devices and browsers |
| **Security Surface** | Token theft gives access to 24h temporary schema | Requires password hashing, MFA, refresh tokens |
| **Compliance (SOC2/GDPR)** | Datasets automatically purge in 24 hours | Requires user data deletion APIs and GDPR logs |

*Migration Path*: When enterprise multi-tenancy is added, the `owner_token_hash` column is easily supplemented with a `user_id uuid REFERENCES users(id)` foreign key.

---

## 7. REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/datasets` | Upload 1-5 files (CSV, TSV, XLSX) and profile into schema `ds_<8hex>` |
| `GET` | `/api/datasets` | List accessible datasets (`olist-demo` + owner datasets) |
| `GET` | `/api/datasets/{id}` | Retrieve comprehensive dataset profile |
| `PATCH` | `/api/datasets/{id}/columns` | Update column roles, user descriptions, confirmed relationships |
| `GET` | `/api/datasets/{id}/preview` | Preview up to 50 rows via `readonly_engine` |
| `DELETE` | `/api/datasets/{id}` | Drop schema `DROP SCHEMA ds_<8hex> CASCADE` and delete metadata |
