# InsightForge AI Infrastructure & Safety Architecture

## 1. Overview
InsightForge Level 1 AI Infrastructure provides a zero-hallucination, secure, and audited backend foundation for AI-powered autonomous business intelligence. The system strictly isolates the LLM from raw database credentials and direct execution rights, enforcing verification and provenance at every stage.

---

## 2. Security & Database Access Control
- **Read-Only Database Role (`insightforge_ro`)**:
  - Provisioned via `database/roles.sql`.
  - Restricted to `SELECT` privileges only on `insightforge` schema tables and views.
  - Defense-in-depth statement execution timeout capped at 5 seconds:
    `ALTER ROLE insightforge_ro SET statement_timeout = '5s';`
- **Read-Only SQLAlchemy Engine (`readonly_engine`)**:
  - Located in `backend/app/database.py`.
  - Configured with `connect_args={"options": "-c statement_timeout=5000"}`.
  - Analytical and AI grounding queries utilize this engine to prevent writes, table drops, or runaway queries.

---

## 3. Query Audit Logging (`AIAuditService`)
- **Table**: `insightforge.ai_audit_log`
  - Columns:
    - `id SERIAL PRIMARY KEY`
    - `question TEXT NOT NULL`
    - `intent VARCHAR(100)`
    - `generated_sql TEXT`
    - `latency_ms DOUBLE PRECISION NOT NULL`
    - `success BOOLEAN NOT NULL`
    - `error TEXT`
    - `timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- **Service**: `backend/app/services/audit_service.py`
  - Persists query telemetry to PostgreSQL with automatic in-memory ring-buffer fallback.
- **API Endpoint**:
  - `GET /api/ai/history?limit=50`: Returns recent natural-language queries, classified intents, latency, and status.

---

## 4. Numeric Faithfulness & Grounding Verifier
- **Location**: `backend/app/services/grounding.py`
- **Mechanism**:
  - Extracts formatted numeric entities (currency amounts, integers, floats, percentages) from LLM-generated explanations.
  - Recursively traverses the analytics evidence payload returned by PostgreSQL analytics functions.
  - Compares all extracted numbers against evidence values within a relative tolerance (default: 1.0%), taking percent/fraction conversions into account.
  - Allows structural metadata numbers (e.g. dataset years 2016–2018, top-N ranks `#1`–`#10`).
- **Safety Fallback**:
  - If any number in the answer is not backed by the evidence payload (hallucination detected), the service discards the LLM synthesis, falls back to the deterministic heuristic synthesis, and marks `grounding_verified: false` in `AskAIResponse`.

---

## 5. Offline Evaluation Suite
- **Dataset**: `backend/evals/golden_questions.yaml`
  - 55 curated questions:
    - 40 domain questions across 8 business domains (category, state, seller, delivery, payment, trend, KPIs, data quality)
    - 10 out-of-scope questions (weather, general programming, sports, trivia)
    - 5 ambiguous questions
- **Evaluation Runner**: `backend/evals/run_eval.py`
  - Supports `--mode heuristic` (offline rule-based intent classification & synthesis) and `--mode gemini` (live Google Gemini 2.5 Flash classification & synthesis).
  - Evaluates intent classification accuracy and canonical numeric faithfulness.
  - Formats output table labeled with active mode (`HEURISTIC` vs `GEMINI`).

---

## 6. Rate Limiting
- Built using `slowapi` with client IP address keying (`get_remote_address`).
- Enforces `@limiter.limit(settings.RATE_LIMIT_AI_ASK)` on `POST /api/ai/ask` (default: 30 requests/minute) to mitigate denial-of-service and API abuse.

---

## 7. Containerization & CI/CD
- **`docker-compose.yml`**: Provisions multi-container environment with `postgres:15-alpine`, `backend` (FastAPI), and `frontend` (React + Nginx).
- **GitHub Actions (`.github/workflows/ci.yml`)**:
  - Runs unit tests and golden question evaluations against seeded PostgreSQL in CI.
  - Runs frontend TypeScript typechecking (`npx tsc --noEmit`) and production build.

---

## 8. Level 1.5: Strict Fixture Policy & Database Availability
- **Removal of Silent Fallbacks**:
  - All silent fallbacks to canonical/hardcoded fixtures across analytical services, data quality, and AI routing have been eliminated.
  - When PostgreSQL is disconnected, analytical services raise `DatabaseUnavailableError` (`backend/app/exceptions.py`).
- **Opt-In Fixture Mode (`USE_FIXTURES=1`)**:
  - Fixtures are active **ONLY** when environment variable `USE_FIXTURES=1` is explicitly set (used in headless testing and CI where no live PostgreSQL service exists).
  - In normal production and development, if the database is down, the system fails loudly and honestly.
- **API Behavior on Database Failure**:
  - FastAPI endpoints return `HTTP 503 Service Unavailable` with `{"detail": "Database unavailable"}`.
  - The actual low-level connection trace is logged server-side without exposing credentials or internal topology to clients.
- **Truthful Health Reporting & UI Demo Badge**:
  - `/api/health` includes `data_source: "postgres" | "fixture"` and truthfully reports `database: "disconnected"` when offline.
  - When `data_source == "fixture"`, the React frontend displays a prominent **"DEMO DATA"** badge in the header navigation bar.
  - When endpoints return 503, the frontend displays an `ErrorBanner` rather than empty or fabricated charts.
