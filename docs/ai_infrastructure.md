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
  - Runs offline without requiring an active database or live Gemini API key.
  - Evaluates heuristic intent classification accuracy and canonical numeric faithfulness.
  - Outputs a detailed per-category breakdown and benchmark summary.

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
