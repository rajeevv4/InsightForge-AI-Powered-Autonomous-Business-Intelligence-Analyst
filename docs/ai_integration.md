# InsightForge — Initial AI Integration Architecture & Design Specification

> **Step 6 Initial AI Capability**: "Ask InsightForge"  
> **Status**: Verified & Operational  
> **LLM Model**: Google Gemini (`gemini-2.5-flash`) via `google-genai` Python SDK  

---

## 1. Why AI Was Added

While InsightForge provides validated PostgreSQL views, executive KPI dashboards, and interactive charts, business users often need to ask natural-language questions without navigating complex dashboards or writing database queries.

The goal of this initial AI integration ("Ask InsightForge") is to provide a reliable, conversational interface for business stakeholders that:
- Translates natural-language business questions into validated intent execution.
- Eliminates AI hallucinations by grounding explanations exclusively in real PostgreSQL data.
- Enforces strict security boundaries to prevent SQL injection or un-audited code execution.

---

## 2. Technical Architecture

The LLM is strictly isolated from direct database access. All data retrieval occurs through the pre-validated analytics layer.

```
[User Question]
       │
       ▼
[FastAPI: POST /api/ai/ask]
       │
       ▼
[AIService] ──────────► [Gemini 2.5 Flash] (Intent Classification)
       │                         │
       │ (Confidence >= 0.60)    ▼
       │                    Structured Intent: "category_analysis"
       ▼
[AIAnalyticsRouter]
       │
       ▼
[AnalyticsService / DataQualityService] ──► [PostgreSQL Views]
       │                                           │
       ▼                                           ▼
Standardized Evidence Object ◄─────────────────────┘
       │
       ▼
[AIService] ──────────► [Gemini 2.5 Flash] (Grounded Synthesis)
       │                         │
       │                         ▼
       └────────────────► Structured JSON Response
                                 │
                                 ▼
                     [React Dashboard: Ask InsightForge Component]
```

---

## 3. Gemini's Role

Gemini is used for two specific, constrained capabilities:
1. **Intent Classification**: Mapping free-form natural language questions to one of 8 allow-listed business intents with confidence scoring.
2. **Grounded Synthesis**: Translating structured JSON analytics evidence into clear, professional, human-readable executive summaries.

Gemini does **NOT**:
- Generate or execute SQL queries.
- Direct-connect to PostgreSQL database instances.
- Execute arbitrary Python or shell code.
- Fabricate or estimate numerical figures.

---

## 4. Intent Classification System

Supported business intents are strictly limited to an allow-list:

| Intent Name | Scope / Target Metric | Target Analytics Function |
|---|---|---|
| `kpi_summary` | Executive KPIs (Revenue, AOV, Orders, CSAT) | `AnalyticsService.fetch_canonical_kpis()` |
| `revenue_trend` | Monthly revenue, order volume, MoM growth | `AnalyticsService.fetch_revenue_trend()` |
| `category_analysis` | Product category sales, revenue share, prices | `AnalyticsService.fetch_categories(limit=10)` |
| `state_analysis` | Geographic state sales distribution & customers | `AnalyticsService.fetch_states()` |
| `seller_analysis` | Top seller fulfillment & seller revenue | `AnalyticsService.fetch_sellers(limit=10)` |
| `payment_analysis` | Payment method breakdown & installments | `AnalyticsService.fetch_payments()` |
| `delivery_analysis` | Delivery SLA performance, delay rates, days | `AnalyticsService.fetch_delivery_performance()` |
| `data_quality` | Database row counts, missing values, audits | `DataQualityService.fetch_audit_summary()` |

### Confidence Thresholding
- **Confidence Definition**: Confidence measures AI certainty in matching user intent. It is **not** a statistical confidence interval.
- **Cutoff**: If confidence is below `0.60`, database analytics are **not** executed. The system returns a polite rephrase prompt asking the user to clarify their business question.

---

## 5. Controlled Analytics Routing

The `AIAnalyticsRouter` maps intent strings directly to static, audited Python functions. No SQL strings are constructed dynamically from user input.

```python
# Conceptual snippet from ai_analytics_router.py
if intent == "category_analysis":
    data = AnalyticsService.fetch_categories(limit=10)
    metric = "Product Category Performance & Revenue Share"
```

---

## 6. Semantic Layer Integration

To ensure the AI understands company terminology, metric definitions, and column grains, `AIService` automatically reads the machine-readable semantic layer specifications:
- `semantic/business_glossary.yaml`
- `semantic/metrics.yaml`
- `semantic/dimensions.yaml`
- `semantic/relationships.yaml`

This context is injected into Gemini's system instructions during grounded answer synthesis.

---

## 7. Evidence Grounding Rules

The prompt given to Gemini for generating natural language explanations includes strict guardrails:
1. Use **only** the provided evidence payload.
2. Do **not** invent numbers, percentages, or dates.
3. Do **not** claim causality unless explicitly supported by evidence.
4. If evidence is insufficient, explicitly state limitations.
5. Distinguish contribution/correlation from causation.

---

## 8. Security Controls

- **API Key Protection**: `GEMINI_API_KEY` is loaded exclusively via backend environment variables (`.env`). It is never passed to frontend client code or logged in error messages.
- **Input Validation**: `AskAIRequest` enforces string whitespace trimming, minimum length (3 chars), and maximum length (500 chars).
- **Graceful Error Handling**: Uncaught backend exceptions return safe generic HTTP 500 error messages without exposing database connection strings, API keys, or tracebacks.
- **Offline / Fallback Reliability**: Includes heuristic rule-based classification and synthesis fallbacks so automated test suites and offline environments execute deterministically.

---

## 9. System Limitations

- **Arbitrary Text-to-SQL**: Not supported in Step 6 by design (will be evaluated in future phases with schema sandboxing).
- **Multi-Turn Chat History**: Current endpoint evaluates single-turn business questions.
- **Multi-Agent Orchestration**: Multi-agent routing (LangGraph/MCP) is planned for future architecture steps.

---

## 10. Example Supported Questions

1. *"Which category generated the highest revenue?"* → `category_analysis`
2. *"What is our average order value?"* → `kpi_summary`
3. *"Which state has the highest sales?"* → `state_analysis`
4. *"How is our delivery performance?"* → `delivery_analysis`
5. *"Which payment method is most common?"* → `payment_analysis`
6. *"Give me a summary of our current KPIs."* → `kpi_summary`

---

## 11. Test Results

### Automated Test Suite Execution
```bash
python3 -m unittest discover -s backend/tests
```
- **Total Tests**: 17 passed (9 core API/analytics tests + 8 new AI API tests).
- **Mocking**: All AI tests use mocked Gemini responses ensuring deterministic offline execution.

### Semantic Layer Validation
```bash
python3 semantic/validate_semantic_layer.py
python3 semantic/test_semantic_layer.py
```
- **Glossary Terms**: 19 validated.
- **Metrics**: 8 validated.
- **Dimensions**: 9 validated.
- **Relationships**: 6 validated.
