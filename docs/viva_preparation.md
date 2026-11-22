# InsightForge — Viva & Project Defense Guide

> **B.Tech Major Project**  
> **Project Title**: InsightForge: AI-Powered Autonomous Business Intelligence Analyst  
> **Authors**: **Rajeev Karakoti**, **Priyanshu Saklani**, **Prasanna Godiyal**  
> **Dataset**: Olist Brazilian E-Commerce (~100,000 orders, Currency: Brazilian Real `R$`)  
> **Stack**: FastAPI (Python 3.12), PostgreSQL 15+ (Docker Compose & CI use `postgres:15-alpine`; also run on PostgreSQL 16 locally and 17 on Supabase), React 18 + TypeScript + Vite + TailwindCSS, Google Gemini 2.5 Flash, Docker, GitHub Actions  

---

## 🎯 1. Project Vision & Problem Statement

### The Problem
- **Traditional BI Dashboards** (Tableau, PowerBI) are static and inflexible. Stakeholders must wait days or weeks for data engineering teams to build new charts for ad-hoc business questions.
- **Naive "Text-to-SQL" LLM Solutions** suffer from three catastrophic enterprise failure modes:
  1. **Hallucination**: LLMs fabricate non-existent numbers, wrong column names, or incorrect financial calculations.
  2. **Security Vulnerabilities**: Giving an LLM raw database credentials allows prompt injection, data exfiltration, or accidental drop/update operations.
  3. **Cartesian Fan-Out / Multiplication**: Naive SQL joins between 1-to-many tables (e.g. `order_items` joined directly with `order_reviews` and `order_payments`) multiply revenues by up to 200–300%, producing completely invalid balance sheets.

### The InsightForge Solution
InsightForge introduces a **Controlled, Evidence-Grounded Autonomous BI Architecture**:
1. **Semantic Layer First**: Natural language is parsed into allow-listed business intents mapped to pre-audited analytical views.
2. **Database Isolation**: The LLM *never receives database credentials* and *never executes arbitrary SQL*.
3. **Read-Only Database Sandboxing**: Analytics queries execute against an isolated read-only role (`insightforge_ro`) with a 5-second statement timeout.
4. **Deterministic Grounding Verification**: Every numerical figure in the LLM's explanation is extracted via regular expressions and verified against the computed evidence payload before reaching the user. Any discrepancy immediately triggers a deterministic fallback synthesis.

---

## 🏛 2. System Architecture Flow

```
+-----------------------------------------------------------------------------------+
|                                  USER / BROWSER                                   |
|                        React 18 + TypeScript + Tailwind CSS                       |
+-----------------------------------------------------------------------------------+
                                          |
                        HTTP REST API (JSON, BRL / R$)
                                          v
+-----------------------------------------------------------------------------------+
|                                FASTAPI BACKEND                                    |
|                                                                                   |
|  [Rate Limiter (SlowAPI 30/min)]                                                  |
|       |                                                                           |
|  [AI Analytics Router]                                                            |
|       |--> Intent Classification (Gemini 2.5 Flash / Regex Word-Boundary Fallback) |
|       |--> Route to Pre-Audited SQL Analytical Views / Services                   |
|       |                                                                           |
|  [Database Engine Isolation]                                                      |
|       |--> Read-Write Engine (Application schema & migrations)                   |
|       |--> Read-Only Engine (`insightforge_ro`, 5s statement_timeout)             |
|       |                                                                           |
|  [Evidence Fetching from PostgreSQL 15+ (Schema: `insightforge`)]                 |
|       |--> Executed over Olist E-commerce data (Delivered orders only)            |
|       |                                                                           |
|  [Grounded Synthesis & Verification]                                              |
|       |--> Synthesize narrative explanation using Evidence Payload                |
|       |--> `verify_numeric_grounding()`: Regex token validation (Tolerance ±0.05) |
|       |    * PASS: Return LLM explanation with grounding_verified=True           |
|       |    * FAIL: Discard LLM output, fallback to deterministic synthesis       |
|       |                                                                           |
|  [AI Audit Logger]                                                                |
|       |--> Asynchronously logs question, intent, latency, success to audit table   |
+-----------------------------------------------------------------------------------+
```

---

## 🛡 3. The Four Non-Negotiable Core Engineering Pillars

### Pillar 1: Financial Correctness & Fan-Out Prevention
- **The Fan-Out Bug**: An order with 3 items and 2 payments or reviews creates $3 \times 2 = 6$ joined rows if joined directly. Summing `oi.price` multiplies revenue!
- **Our Fix**:
  - In `view_category_contribution` and `view_seller_performance`, we aggregate `order_reviews` to order-level average scores in a **Common Table Expression (CTE)** (`GROUP BY r.order_id`) *before* joining to `order_items`.
  - Financial KPIs strictly filter by `order_status = 'delivered'`.
  - Invariant: The sum of category revenue equals canonical product revenue **R$ 13,221,498.11**, and category contribution percentages sum to **~100.00%** (enforced by unit tests with tolerance 99.9%–100.1%).

### Pillar 2: Read-Only Role & Database Sandboxing
- **Role**: `insightforge_ro` defined in `database/roles.sql`.
- **Permissions**: `CONNECT` on database, `USAGE` on schema `insightforge`, `SELECT` on tables/views only. `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` are blocked at the engine level.
- **Statement Timeout**: Set to `statement_timeout = '5s'` to prevent Denial of Service (DoS) from heavy analytical queries.
- **Separate Connection Pool**: `readonly_engine` in `backend/app/database.py` with SQLAlchemy connection pooling (`pool_pre_ping=True`).

### Pillar 3: Grounding Verification (Zero Hallucination)
- **Implementation**: `backend/app/services/grounding.py`.
- **Algorithm**:
  1. Tokenizes all numerical values in LLM output using boundary-safe regex: `r"(?:\bR\$\s*|\b|\$)(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?%?)\b"`.
  2. Extracts all scalar numbers from the structured PostgreSQL evidence payload recursively.
  3. Compares every extracted answer number against evidence with a fuzzy tolerance:
     $$\Delta \le 0.05 \quad \text{or} \quad \frac{|n_{\text{ans}} - n_{\text{evi}}|}{n_{\text{evi}}} \le 0.015 \quad (1.5\%)$$
  4. Exempts legitimate contextual metadata: calendar years (2016–2026), ranks (1–10), and zero.
  5. If an ungrounded number is found, the system rejects the LLM answer, triggers deterministic heuristic synthesis, flags `grounding_verified = False`, and logs the event.

### Pillar 4: Automated Data Quality Engine
- **Implementation**: `database/data_quality.py` and `backend/app/services/data_quality_service.py`.
- Replaced all hardcoded status strings with **real computed database audits**:
  1. **Primary Key Uniqueness**: `COUNT(*) - COUNT(DISTINCT pk)` across all 7 core tables.
  2. **Foreign Key Referential Integrity**: Checks for orphan records across joins.
  3. **Domain Bounds & Non-Negativity**: Validates `price > 0`, `freight_value >= 0`, `review_score BETWEEN 1 AND 5`.
  4. **Missing Value Tracking**: Quantifies nulls in optional timestamps (e.g., `order_delivered_customer_date`).
  5. **Join Safety Check**: Compares direct sum of `order_items.price` against `view_order_level_summary.total_product_amount` (discrepancy = 0.00).

---

## 📊 4. Canonical Metrics & Benchmark Invariants

| Business Metric | Canonical Value | SQL Calculation / Formula | Business Meaning |
|---|---|---|---|
| **Product Revenue** | **R$ 13,221,498.11** | `SUM(oi.price) WHERE o.order_status = 'delivered'` | Net merchandise sales |
| **Freight Revenue** | **R$ 2,198,275.64** | `SUM(oi.freight_value) WHERE o.order_status = 'delivered'` | Total logistics fees billed |
| **Gross Revenue** | **R$ 15,419,773.75** | `Product Revenue + Freight Revenue` | Total revenue inflow |
| **Delivered Orders** | **96,478** | `COUNT(DISTINCT order_id) WHERE order_status = 'delivered'` | Successfully fulfilled orders |
| **Average Order Value (AOV)** | **R$ 159.83** | `Gross Revenue / Total Delivered Orders` | Mean gross spend per order |
| **Customer Satisfaction (CSAT)** | **4.16 / 5.0** | `AVG(review_score) WHERE order_status = 'delivered'` | Mean customer review score |
| **Delivery SLA On-Time %** | **91.88%** | `88,644 / 96,478 * 100` | Orders delivered on or before estimate (avg 10.9 days to deliver) |
| **Delivery SLA Delayed %** | **8.11%** | `7,826 / 96,478 * 100` | Orders delivered past estimated SLA (avg 9.6 days late) |
| **Delivery SLA Undelivered** | **8 orders (0.01%)** | status `delivered` but `order_delivered_customer_date IS NULL` | Data-quality edge case, kept visible rather than hidden |
| **Avg Delivery Time (all delivered)** | **12.6 days** | `AVG(actual_delivery_days)` over `view_delivery_sla_performance` | Purchase → customer delivery |
| **Top State by Gross Revenue** | **São Paulo (SP)** | **R$ 5,769,703.15 (38.33%)** | Largest regional consumer market (product R$ 5,067,633.16 + freight) |
| **Top Category by Revenue** | **health_beauty** | **R$ 1,233,131.72 (9.33%)** | Leading product category (product revenue) |

---

## 🛠 5. Level 0 & Level 1 Implementation Summary

### Level 0: Correctness & Soundness
- **Fixed Views**: Eliminated Cartesian join fan-out in `view_category_contribution` and `view_seller_performance` by pre-aggregating review scores per order. Category contribution now sums strictly to 100.00%.
- **Real Data Quality**: Connected frontend cards and tables to real computed SQL queries for PK, FK, domain bounds, null values, and join safety.
- **Semantic Synonyms**: Updated `business_glossary.yaml` to handle top-level terms and business synonyms.
- **Currency Standardization**: Replaced all INR (`₹`) references with Brazilian Real (`R$`).
- **Word-Boundary Heuristic Regex**: Enhanced classifier with `\b` word boundaries to eliminate false positives on sub-words (e.g., "moment", "estate", "slack").
- **Pooled SQLAlchemy Engine**: Swapped per-call engine instantiation with a pooled module-level engine.
- **Generic 500 Responses**: Sanitized API error responses to prevent internal stack trace leakage.
- **Dead Code Cleanup**: Deleted legacy unused files (`frontend/src/pages/Dashboard.tsx`, `Header.tsx`).

### Level 1: Infrastructure for AI Features
- **Read-Only Database Role**: Created `insightforge_ro` role with `statement_timeout = 5s` and configured secondary `readonly_engine`.
- **AI Audit Logging**: Built `AIAuditService` logging question, intent, latency, SQL/evidence route, success flag, and error with `GET /api/ai/history?limit=`.
- **Golden Evaluation Suite**: Designed `golden_questions.yaml` (now 113 questions: 83 intent cases — 48 domain, 10 out-of-scope, 5 ambiguous, 20 multilingual — plus 30 Text-to-SQL cases) and `run_eval.py` CLI runner scoring **97.59% intent accuracy** and **100.00% numeric faithfulness** (live DB).
- **Grounding Verifier**: Built `verify_numeric_grounding()` in `grounding.py` with heuristic fallback on ungrounded hallucination.
- **Rate Limiting**: Integrated `slowapi` on `POST /api/ai/ask` (default 30 requests/minute).
- **Docker Compose & CI**: Configured multi-container deployment (`docker-compose.yml`) and automated GitHub Actions CI workflow running full test suites and builds.
- **Rule 5 Compliance**: Created `fixture_guard.py` enforcing `USE_FIXTURES=1` flag so that production never serves silent fake data.

---

## 💡 6. Top 25 Viva Q&A — Rapid-Fire Examiner Defense

#### Q1: What is the primary objective of InsightForge?
> **Answer**: InsightForge is an autonomous Business Intelligence analyst that allows non-technical business stakeholders to ask questions in natural language and receive verified, zero-hallucination insights, complete with evidence data and interactive charts, without needing SQL knowledge or risking database security.

#### Q2: Why did you choose the Olist Brazilian E-Commerce dataset?
> **Answer**: Olist provides real-world multi-table relational complexity (~100,000 orders across 7 core tables: orders, items, products, customers, sellers, payments, reviews) with messy real-world challenges: 1-to-many relationships, cancellations, delivery delays, and multiple payment installments.

#### Q3: Why doesn't your LLM write SQL directly?
> **Answer**: Direct Text-to-SQL in production has critical flaws: LLMs can hallucinate non-existent table schemas, generate catastrophic full-table scans, write invalid JOINs that cause fan-out multiplication, or be vulnerable to prompt injection. Instead, we use an Allow-Listed Semantic Router where the LLM only classifies intent, and pre-audited, optimized PostgreSQL views execute the math.

#### Q4: How did you fix the Cartesian fan-out issue in your views?
> **Answer**: In `view_category_contribution`, an order can have multiple items and multiple reviews. Joining `order_items` directly to `order_reviews` duplicates item prices for every review row. We solved this by creating a CTE that calculates `AVG(review_score)` grouped by `order_id` (1 row per order) and joins that CTE to `order_items`.

#### Q5: How do you verify that the LLM is not hallucinating numbers?
> **Answer**: We developed a deterministic Grounding Verifier (`grounding.py`). It uses regular expressions to extract every number, currency, or percentage from the LLM's narrative response and recursively checks if that number exists in the structured PostgreSQL evidence payload within a tolerance of $\pm 0.05$ or $1.5\%$. If any number fails, the response is rejected and replaced with deterministic synthesis.

#### Q6: How is database security enforced against AI features?
> **Answer**: We created a dedicated PostgreSQL role `insightforge_ro` with `SELECT` privileges only on tables and views in the `insightforge` schema. It cannot execute `INSERT`, `UPDATE`, `DELETE`, or `DROP`. Furthermore, `statement_timeout` is capped at 5 seconds to prevent runaway analytical queries.

#### Q7: What currency does InsightForge use and why?
> **Answer**: Brazilian Real (`R$`, BRL), because the underlying Olist dataset is from Brazil. All frontend charts, KPI cards, and heuristic answers use `R$`.

#### Q8: What is your Average Order Value (AOV) and how is it calculated?
> **Answer**: AOV is **R$ 159.83**. It is calculated strictly on delivered orders as:
> $$\text{AOV} = \frac{\text{Total Gross Revenue (Product + Freight)}}{\text{Total Delivered Orders}} = \frac{\text{R\$ 15,419,773.75}}{96,478} = 159.83$$

#### Q9: What is the delivery SLA performance in the dataset?
> **Answer**: Out of 96,478 delivered orders, **91.88% (88,644 orders)** were delivered on or before the estimated delivery date (On-Time), while **8.11% (7,826 orders)** were delayed past the estimated date by an average of **9.6 days**. The remaining **8 orders (0.01%)** are marked `delivered` but have no delivery date, so they are reported as "Undelivered" instead of being silently counted. On-time orders took **10.9 days** on average; across all delivered orders the average delivery time is **12.6 days**.

#### Q10: How do you handle Month-over-Month (MoM) growth calculations in SQL?
> **Answer**: In `view_monthly_kpis_mom`, we use SQL window functions: `LAG(gross_revenue) OVER (ORDER BY sales_month)`. To prevent division by zero errors, we wrap the denominator in `NULLIF(LAG(...), 0)`.

#### Q11: How do you prevent denial-of-service or bot abuse on your AI endpoint?
> **Answer**: We implemented API rate limiting using `slowapi` on `POST /api/ai/ask`, restricting clients to a default of 30 requests per minute by remote IP address.

#### Q12: How do you audit AI interactions?
> **Answer**: Every question sent to `/api/ai/ask` is recorded via `AIAuditService` into the `insightforge.ai_audit_log` table with columns: question, intent, latency in milliseconds, evidence route, success boolean, error message, and timestamp. It is queryable via `GET /api/ai/history`.

#### Q13: How do you measure the quality of your AI system?
> **Answer**: We built an Evaluation Benchmark (`evals/run_eval.py`) over `golden_questions.yaml`, which has **113 golden questions**: 83 intent/answer cases (48 domain, 10 out-of-scope, 5 ambiguous, 20 Hindi/Hinglish multilingual) plus 30 Text-to-SQL cases. Three extra hold-out files add 80 more (30 + 30 + 20 SQL). Latest measured results:
> 1. **Intent Classification Accuracy** (heuristic mode, 83 cases): **97.59%** (81/83).
> 2. **Numeric Faithfulness**: **100.00%** (32/32) against the live database; 93.75% (30/32) in offline fixture mode.
> 3. **Text-to-SQL** (`--mode sql`, 30 cases, Gemini): **100%** valid & executed SQL, **93.3%** (28/30) exact result accuracy.

#### Q14: What is the Semantic Layer and why is it important?
> **Answer**: The semantic layer (`/semantic`) acts as the single source of truth for business metrics and definitions. It defines standardized glossary terms, canonical metric formulas, dimensions, and join safety rules. This prevents different teams from calculating revenue or AOV with conflicting filters.

#### Q15: Why are non-delivered orders excluded from financial KPIs?
> **Answer**: In e-commerce accounting, orders that are cancelled, unavailable, or in-transit cannot be recognized as finalized revenue. Doing so would violate the matching principle and overstate sales.

#### Q16: How do you test your application?
> **Answer**: We run a multi-tier automated test suite:
> 1. Database & Analytics Invariant Tests (`python database/test_analytics.py` - 8 tests).
> 2. Backend API & AI Unit Tests, offline (`USE_FIXTURES=1 python -m unittest discover -s backend/tests` - 277 tests).
> 3. Live Database Integration Tests (`python -m unittest discover -s backend/tests_integration` - 25 tests).
> 4. Semantic Layer Tests (`python semantic/test_semantic_layer.py` - 9 tests).
> 5. AI Golden Question Evals (`python backend/evals/run_eval.py` - 83 intent cases; `--mode sql` - 30 Text-to-SQL cases).
> 6. Frontend Typecheck & Build (`npx tsc --noEmit && npm run build`).

#### Q17: What does Rule 5 (NO silent fake data) mean?
> **Answer**: In production, the system must never silently pretend everything is working by displaying hardcoded mock data when PostgreSQL is down. It must fail loudly with a clear database connection error. Mock fixtures are permitted *only* during automated unit tests or when explicitly enabled via `USE_FIXTURES=1`.

#### Q18: How does your frontend state management and routing work?
> **Answer**: Built with React 18, TypeScript, and React Router v7. State is managed via typed React hooks (`useState`, `useEffect`), and HTTP communication is centralized in an Axios service (`api.ts`) with custom response types.

#### Q19: Which product category contributes the most revenue?
> **Answer**: `health_beauty` generates **R$ 1,233,131.72** (~9.33% of total product revenue), followed by `watches_gifts` with **R$ 1,166,176.98** (~8.82%).

#### Q20: Which state in Brazil generates the most revenue?
> **Answer**: The state of São Paulo (`SP`), generating **R$ 5,769,703.15** gross revenue (~38.33% of total gross revenue), followed by Rio de Janeiro (`RJ`) at 13.31% and Minas Gerais (`MG`) at 11.74%.

#### Q21: What is the most popular payment method?
> **Answer**: Credit card accounts for **78.46%** of total payment value (R$ 12.10M across 74,304 orders) with an average of 3.5 installments, followed by Boleto bancário at **17.96%**.

#### Q22: What happens if the Gemini API key is missing or quota is exhausted?
> **Answer**: InsightForge features an automatic graceful fallback. If Gemini classification fails, it falls back to a regex word-boundary heuristic classifier. If explanation synthesis fails, it uses deterministic heuristic generation so the user is never left with a blank or broken screen.

#### Q23: How do you containerize the project?
> **Answer**: Using Docker Compose with 3 services:
> 1. `postgres:15-alpine` initializing database schema, views, and roles.
> 2. `backend` running FastAPI on Python 3.12-slim.
> 3. `frontend` running a multi-stage Node 20 build served through an Nginx alpine web server.

#### Q24: What CI/CD pipeline have you implemented?
> **Answer**: A GitHub Actions workflow (`.github/workflows/ci.yml`) that spins up PostgreSQL 15, runs the database schema, views, and seed scripts, executes all backend unit tests and AI evaluations, and builds the frontend production bundle on every push and pull request.

#### Q25: What is the significance of the 10 data quality checks?
> **Answer**: Real-world e-commerce data contains missing values, duplicate entries, or orphaned foreign keys. Our automated data quality service monitors 7 core tables for PK collisions, FK orphans, domain bound violations, and joins safety, rendering live audit badges in the UI.

---

## 🎬 7. 5-Minute Live Viva Demo Script

| Minute | Screen / Action | Talk Track |
|---|---|---|
| **0:00 - 1:00** | **Executive Overview Page** | "Welcome, professors. This is InsightForge. Here on the Executive Overview, you see our 6 canonical KPIs: Gross Revenue of R$ 15.42M, Product Revenue of R$ 13.22M, and an AOV of R$ 159.83 across 96,478 delivered orders. Notice that these values are strictly grounded in Olist's delivered orders, with BRL currency formatting throughout." |
| **1:00 - 2:00** | **Ask InsightForge AI** | "Now let's ask an executive question: *'Which product category generated the most revenue?'*. Within 400 milliseconds, InsightForge classifies the intent to `category_analysis`, executes our optimized PostgreSQL view, returns the structured evidence, and uses Google Gemini to synthesize a concise insight. Notice the `Grounding Verified: PASS` badge." |
| **2:00 - 3:00** | **Anti-Hallucination Demo** | "To demonstrate our security guardrails: our LLM never touches the database. If an LLM were to output a fabricated number like 'R$ 999,999.00', our regex Grounding Verifier immediately detects that this number is not present in the evidence payload, rejects the LLM answer, and falls back to a deterministic explanation." |
| **3:00 - 4:00** | **Analytics & Fan-Out Fix** | "Moving to the Analytics tab: here is our Category Revenue Contribution. In earlier implementations, naive SQL joins between items and reviews multiplied revenues by 300%. We resolved this using order-level CTE pre-aggregation. You can see our category contributions sum exactly to 100.00%." |
| **4:00 - 5:00** | **Data Quality & CI/CD** | "Finally, on the Data Quality tab, our system runs a live 10-point audit over 100,000 records, verifying zero primary key duplicates, zero foreign key orphans, and zero revenue join discrepancy. Our entire system is fully tested via 277 offline unit tests, 25 live integration tests, and automated CI/CD in GitHub Actions." |

---

## 🧭 8. The Three New Features in Plain Words

All three work for the **Olist demo** and for **uploaded datasets**. None of them uses AI: numbers come from SQL and
statistics, and every sentence comes from a fixed template.

**1. Explain this anomaly (root-cause waterfall).**
- **What it does.** The Anomalies page tells you *that* revenue jumped on a day; this tells you *why*. Click
  **Explain** on any anomaly row and a drawer splits the jump by category, state, seller and payment type (for
  uploaded datasets: by their own columns).
- **How it shows it.** A waterfall chart starts at "Expected", adds or removes each group's contribution, and ends
  exactly at "Observed". A volume-vs-value card says whether there were *more orders* or *bigger orders*.
- **Example.** Black Friday 2017: R$ 175,178 vs R$ 29,768 expected. Almost all of it was volume (1,147 orders vs
  about 178 normally), and the rise was spread across states rather than one group.

**2. Forecast (baseline with confidence bands).**
- **What it shows.** Sidebar → Forecast predicts the next 1–6 months of a SUM/COUNT metric, with an 80% and a 95%
  band.
- **How it earns trust.** Before showing anything, it tests itself on the last 3 months it hid from the model and
  compares against a naive guess ("same as last month"). It labels itself Good / Fair / Weak.
- **When it refuses.** It **refuses** when the data are too short or too noisy, instead of drawing a confident
  wrong line.
- **Olist result.** Fair (17% error). The page openly says it does not beat the naive guess, because 2018 went flat
  after 2017's growth.

**3. One-click report with PDF.**
- **What it does.** Sidebar → Report (or "Generate report" on Overview / after an upload) builds a summary, KPI
  tiles, trend, breakdowns, the top 5 anomalies with their Feature 1 driver sentence, the Feature 2 forecast and
  the data-quality checks.
- **How it's delivered.** It's shown on screen and as an A4 PDF.
- **How it's built.** It calls the same services as the other pages, so the numbers match exactly. Any section
  that fails just says "Section unavailable: <reason>".

## ❓ 9. Ten Likely Examiner Questions on the New Features

1. **Q: Where does the "why" in Explain come from? Is it AI?**
   A: No AI. For the anomaly day and the previous 14 days we run one grouped SQL query per dimension. Each group's
   contribution = its value on the day minus its usual value. The usual mix is scaled so the groups add up exactly
   to the detector's expected value. So Expected + contributions = Observed, to the cent (verified against pandas).

2. **Q: Why don't you just rank dimensions by "how much the top groups explain"?**
   A: A dimension with 4 groups (payment type) would always "explain 100%", and one with 700 sellers looks shifted
   from noise alone. We rank by *explanatory power × mix shift*. A dimension wins only if the change is concentrated
   in a few of its groups **and** those groups moved differently from their usual share.

3. **Q: How do you avoid double counting in the Olist explanation?**
   A: Only delivered orders, the same as the KPIs. Item revenue and reviews are pre-aggregated to one row per order
   before joining, and payment type uses only the primary payment (payment_sequential = 1). Order counts are never
   split by category or seller, because one order can contain several categories; those tabs are shown as skipped
   with that reason.

4. **Q: What model does the forecast use and why?**
   A: ETS (exponential smoothing) with additive error and a damped trend, with seasonality only when there are at
   least 2 full years. It is simple, explainable and standard for short monthly business series. The damping factor
   is capped at 0.9 so a baseline doesn't extrapolate a growth spurt forever; on Olist this cut the backtest error
   from 25% to 17%.

5. **Q: How do you know the forecast is any good?**
   A: A backtest: refit without the last 3 months, predict them, and measure MAPE (average % error). We compare
   with a naive forecast (repeat last month). The badge is Good ≤ 10%, Fair ≤ 25%, otherwise Weak, and the page says
   whether the model beat naive.

6. **Q: When does the forecast refuse, and isn't refusing a failure?**
   A: It refuses when:
   - there are fewer than 12 clean months and fewer than 90 days of data;
   - MAPE > 40% and it doesn't beat naive;
   - MAPE > 100%;
   - the 80% band is wider than ±35% of the forecast.

   Refusing is the honest outcome. On 40 pure-noise test series it refuses 38, while realistic series pass.

7. **Q: How does the report make sure its numbers equal the other pages?**
   A: It doesn't recompute anything. It calls the same Python services the Overview, Analytics, Anomalies, Forecast
   and Data Quality pages use, directly (not over HTTP), in parallel. Tests check that the KPI values in the PDF text
   equal the service values (e.g. R$ 15,419,773.75 and 96,478 orders).

8. **Q: What happens if the database is slow or one part fails?**
   A: Every section runs independently within a 45-second budget. A section that errors or runs out of time shows
   "Section unavailable: <reason>", and the rest of the report still renders. We saw this live when the remote
   database timed out on the anomaly query. Degraded reports are not cached, so the next click retries.

9. **Q: How is an uploaded dataset kept private in these features?**
   A: Every new endpoint checks the owner token first (wrong or missing token → 403 with a clear message), even
   before a cache hit. Queries use the same read-only path as the rest of the app: a per-dataset database role, an
   SQL AST validator, sqlglot-quoted identifiers and a statement timeout. Joins only follow relationships the user
   confirmed and that cannot multiply rows (N:1).

10. **Q: Can the PDF break on Hindi or Chinese names, or on text like "<b>"?**
    A: No. We register a Unicode font (Arial Unicode on macOS, else DejaVu, which ships with matplotlib), escape all
    text before layout, and fall back to Helvetica with "?" replacement if no font loads. Tests build PDFs with
    Devanagari, Chinese, Arabic and "<tags>&" names.
    - **Limitation:** reportlab does not join complex-script letters, so Devanagari conjuncts can look unjoined.

## 🎬 10. 60-Second Demo per Feature

- **Explain.**
  1. Anomalies (Olist) → row 2017-11-24 → **Explain**.
  2. Point at the headline, the waterfall reconciling to R$ 175,178, the tabs and the volume-vs-value card.
- **Forecast.**
  1. Sidebar → **Forecast**. Point at the bands, Fair badge, "does not beat naive" and the trims under the chart.
  2. Set 6 months, then tick "Exclude flagged anomaly days".
  3. Switch to an uploaded dataset: it shows Good. Pick a noisy metric to show the refusal.
- **Report.**
  1. Overview → **Generate report**. Scroll the preview: summary, tiles, totals lines, anomaly drivers, forecast,
     data quality.
  2. Click **Download PDF** and open page 1.
