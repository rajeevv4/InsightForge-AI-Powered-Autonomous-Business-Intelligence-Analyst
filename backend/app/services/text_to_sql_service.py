"""
InsightForge — Guarded Text-to-SQL Service
==========================================
Generates, validates, self-corrects, and securely executes natural language
business queries into PostgreSQL SELECT statements.
Strictly adheres to:
- Context building from /semantic (metrics, dimensions, fan-out rules, order_status='delivered')
- sqlglot AST validation (single SELECT, allowed tables, no cross joins, limit <= 500)
- Execution ONLY via readonly_engine (statement_timeout=5s)
- Self-correction with up to 2 retries on validation or database error
- Dual-routing policy: intent router (confidence >= 0.8) vs guarded Text-to-SQL
- Grounding verification of generated explanations against row evidence
"""

import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml
import pandas as pd
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import readonly_engine
from backend.app.exceptions import DatabaseUnavailableError
from backend.app.schemas.ai import SQLAskResponse
from backend.app.services.sql_validator import SQLValidator
from backend.app.services.ai_service import AIService
from backend.app.services.ai_analytics_router import AIAnalyticsRouter, SUPPORTED_INTENTS
from backend.app.services.grounding import verify_numeric_grounding
from backend.app.services.audit_service import AIAuditService

logger = logging.getLogger(__name__)

# Core allowed schema catalog for LLM context
SCHEMA_CATALOG: str = """
POSTGRESQL SCHEMA & ALLOWED TABLES (insightforge schema):

1. orders (Core Table)
   - order_id: VARCHAR(32) PRIMARY KEY
   - customer_id: VARCHAR(32) REFERENCES customers(customer_id)
   - order_status: VARCHAR(20) -- VALUES: 'delivered', 'shipped', 'canceled', 'invoiced', 'processing', 'unavailable'
   - order_purchase_timestamp: TIMESTAMP
   - order_approved_at: TIMESTAMP
   - order_delivered_carrier_date: TIMESTAMP
   - order_delivered_customer_date: TIMESTAMP
   - order_estimated_delivery_date: TIMESTAMP

2. order_items (Core Table)
   - order_id: VARCHAR(32) REFERENCES orders(order_id)
   - order_item_id: INT
   - product_id: VARCHAR(32) REFERENCES products(product_id)
   - seller_id: VARCHAR(32) REFERENCES sellers(seller_id)
   - shipping_limit_date: TIMESTAMP
   - price: NUMERIC(10, 2)
   - freight_value: NUMERIC(10, 2)

3. customers (Core Table)
   - customer_id: VARCHAR(32) PRIMARY KEY
   - customer_unique_id: VARCHAR(32)
   - customer_zip_code_prefix: VARCHAR(10)
   - customer_city: VARCHAR(100)
   - customer_state: VARCHAR(5)

4. products (Core Table)
   - product_id: VARCHAR(32) PRIMARY KEY
   - product_category_name: VARCHAR(100)
   - product_category_name_english: VARCHAR(100)
   - product_weight_g: INT
   - product_length_cm: INT
   - product_height_cm: INT
   - product_width_cm: INT

5. sellers (Core Table)
   - seller_id: VARCHAR(32) PRIMARY KEY
   - seller_zip_code_prefix: VARCHAR(10)
   - seller_city: VARCHAR(100)
   - seller_state: VARCHAR(5)

6. order_payments (Core Table)
   - order_id: VARCHAR(32) REFERENCES orders(order_id)
   - payment_sequential: INT
   - payment_type: VARCHAR(20) -- 'credit_card', 'boleto', 'voucher', 'debit_card'
   - payment_installments: INT
   - payment_value: NUMERIC(10, 2)

7. order_reviews (Core Table)
   - review_id: VARCHAR(32) PRIMARY KEY
   - order_id: VARCHAR(32) REFERENCES orders(order_id)
   - review_score: INT -- 1 to 5
   - review_creation_date: TIMESTAMP
   - review_answer_timestamp: TIMESTAMP

CANONICAL ANALYTICAL VIEWS:
- view_order_level_summary (order_id, customer_id, order_status, order_purchase_timestamp, item_count, total_product_amount, total_freight_amount, gross_order_amount)
- view_monthly_kpis_mom (sales_month, total_orders, product_revenue, freight_revenue, gross_revenue, aov, mom_revenue_growth_pct)
- view_category_contribution (category_name, category, total_orders, units_sold, total_revenue, avg_item_price, avg_review_score, revenue_contribution_pct)
- view_state_contribution (customer_state, active_customers, total_orders, total_product_revenue, total_freight_revenue, total_gross_revenue, avg_freight_cost, revenue_contribution_pct)
- view_delivery_sla_performance (delivery_status, orders_count, percentage, avg_actual_delivery_days, avg_estimated_delivery_days, avg_delay_days)
- view_seller_performance (seller_id, seller_state, total_orders_fulfilled, units_sold, unique_products_offered, total_sales_revenue, avg_seller_review_score)
"""


class TextToSQLService:
    """
    Guarded Text-to-SQL generation and execution engine.
    """

    @classmethod
    def load_semantic_rules(cls) -> str:
        """
        Loads metrics definitions, synonyms, and join rules from the /semantic directory.
        """
        semantic_dir = Path(__file__).resolve().parent.parent.parent.parent / "semantic"
        rules_text: List[str] = [
            "CRITICAL BUSINESS & JOIN RULES:",
            "1. Financial KPIs (revenue, gross revenue, product sales, AOV) MUST count ONLY delivered orders: WHERE order_status = 'delivered' (or query from analytical views which pre-filter delivered orders).",
            "2. FAN-OUT JOIN RULE: NEVER join order_reviews or order_payments directly to order_items when summing revenue. Instead, use view_order_level_summary or compute sums in a CTE before joining.",
            "3. Currency is Brazilian Real (BRL, symbol R$).",
            "4. Always alias aggregated columns cleanly (e.g. total_revenue, order_count, avg_order_value).",
            "5. The query must be exactly ONE standalone PostgreSQL SELECT statement. No DDL, no DML, no cross joins."
        ]

        metrics_file = semantic_dir / "metrics.yaml"
        if metrics_file.exists():
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        m_list = []
                        for k, v in data.items():
                            if isinstance(v, dict):
                                m_list.append(f"- {v.get('name', k)}: {v.get('formula', '')}")
                        if m_list:
                            rules_text.append("\nCANONICAL METRIC FORMULAS:\n" + "\n".join(m_list))
            except Exception as e:
                logger.warning(f"Could not read metrics.yaml: {e}")

        glossary_file = semantic_dir / "business_glossary.yaml"
        if glossary_file.exists():
            try:
                with open(glossary_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        g_list = []
                        for k, v in data.items():
                            if isinstance(v, dict):
                                syn = v.get("synonyms", [])
                                syn_str = f" (synonyms: {', '.join(syn)})" if syn else ""
                                g_list.append(f"- {v.get('name', k)}: {v.get('definition', '')}{syn_str}")
                        if g_list:
                            rules_text.append("\nBUSINESS GLOSSARY & SYNONYMS:\n" + "\n".join(g_list))
            except Exception as e:
                logger.warning(f"Could not read business_glossary.yaml: {e}")

        return "\n".join(rules_text)

    @classmethod
    def build_generation_prompt(cls, question: str, previous_error: Optional[str] = None, previous_sql: Optional[str] = None) -> str:
        """
        Builds system prompt for Gemini structured JSON output.
        """
        semantic_context = cls.load_semantic_rules()

        correction_section = ""
        if previous_error and previous_sql:
            correction_section = f"""
CRITICAL SELF-CORRECTION NOTICE:
Your previous generated SQL was REJECTED:
Previous SQL:
```sql
{previous_sql}
```
Validation/Database Error:
"{previous_error}"

Please fix this error immediately in your new query. Ensure all referenced tables are from the allowed catalog, do not join order_items with order_reviews/payments when summing, and output a valid PostgreSQL SELECT statement.
"""

        prompt = f"""
You are InsightForge's Expert PostgreSQL Data Analyst.
Your task is to convert the natural language business question into a single, highly performant, guarded PostgreSQL SELECT query.

{SCHEMA_CATALOG}

{semantic_context}

{correction_section}

USER QUESTION: "{question}"

You must respond ONLY with a valid JSON object matching the following schema:
{{
  "sql": "SELECT ...",
  "explanation": "Concise 1-3 sentence grounded explanation describing what data was calculated to answer the question.",
  "assumptions": ["List of any filters, defaults, or date bounds applied, e.g. order_status='delivered'"],
  "suggested_chart": "bar" | "line" | "pie" | "table"
}}

CHART SELECTION GUIDELINES:
- "line": Time series metrics over time (by month, week, or day).
- "bar": Category, state, seller, or payment method rankings.
- "pie": Proportional breakdown across <= 6 distinct segments.
- "table": Detailed records, multiple attributes, or tabular views.

Do NOT include any markdown code blocks or text outside the JSON object.
"""
        return prompt.strip()

    @classmethod
    def execute_guarded_sql(cls, sanitized_sql: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Executes sanitized SQL strictly through readonly_engine with 5s timeout.
        Returns (rows, column_names).
        """
        try:
            with readonly_engine.connect() as conn:
                result = conn.execute(text(sanitized_sql))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchmany(500)]
                return rows, columns
        except Exception as e:
            err_msg = str(e)
            logger.error(f"SQL execution failed on readonly_engine: {err_msg}")
            # Detect DB connectivity issues vs SQL query execution syntax errors
            if "could not connect" in err_msg.lower() or "connection refused" in err_msg.lower() or "password authentication failed" in err_msg.lower() or "is the server running" in err_msg.lower():
                raise DatabaseUnavailableError(f"Database unavailable: Text-to-SQL requires an active PostgreSQL connection. ({err_msg})")
            raise

    @classmethod
    def generate_and_validate_sql(
        cls,
        client: Any,
        question: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Generates SQL via Gemini with self-correction retry loop on validation/execution error.
        """
        attempt = 0
        last_error = None
        last_sql = None

        while attempt <= max_retries:
            prompt = cls.build_generation_prompt(question, previous_error=last_error, previous_sql=last_sql)
            try:
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt
                )
                text_resp = response.text.strip()
                # Remove possible markdown fences ```json ... ```
                cleaned_json = re.sub(r"^```(?:json)?\s*", "", text_resp, flags=re.MULTILINE)
                cleaned_json = re.sub(r"\s*```$", "", cleaned_json, flags=re.MULTILINE).strip()
                parsed_json = json.loads(cleaned_json)

                raw_sql = parsed_json.get("sql", "")
                last_sql = raw_sql

                # 1. AST Validation
                is_valid, sanitized_sql, val_error = SQLValidator.validate(raw_sql)
                if not is_valid:
                    last_error = f"Validation Error: {val_error}"
                    logger.warning(f"Text-to-SQL attempt {attempt + 1} validation failed: {last_error}")
                    attempt += 1
                    continue

                # 2. Database Execution
                rows, cols = cls.execute_guarded_sql(sanitized_sql)

                return {
                    "success": True,
                    "sql": sanitized_sql,
                    "explanation": parsed_json.get("explanation", "Query executed successfully."),
                    "assumptions": parsed_json.get("assumptions", []),
                    "suggested_chart": parsed_json.get("suggested_chart", "table"),
                    "rows": rows,
                    "columns": cols,
                    "row_count": len(rows),
                    "attempts": attempt + 1
                }

            except DatabaseUnavailableError:
                raise
            except Exception as e:
                last_error = f"Execution/Format Error: {str(e)}"
                logger.warning(f"Text-to-SQL attempt {attempt + 1} failed: {last_error}")
                attempt += 1

        return {
            "success": False,
            "sql": last_sql,
            "explanation": "Unable to safely generate a validated SQL query for this question.",
            "assumptions": [],
            "suggested_chart": "table",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "error": last_error,
            "attempts": attempt
        }

    @classmethod
    def synthesize_fallback_explanation(cls, rows: List[Dict[str, Any]], columns: List[str]) -> str:
        """Generates deterministic heuristic explanation when Gemini explanation fails grounding."""
        if not rows:
            return "The database query executed successfully but returned 0 matching records."
        if len(rows) == 1:
            row = rows[0]
            summary_parts = []
            for col, val in row.items():
                if isinstance(val, (int, float)):
                    val_str = f"R$ {val:,.2f}" if "price" in col or "revenue" in col or "amount" in col else f"{val:,.2f}"
                    summary_parts.append(f"{col}: **{val_str}**")
                else:
                    summary_parts.append(f"{col}: `{val}`")
            return "Query result: " + ", ".join(summary_parts) + "."
        return f"Query returned **{len(rows)}** records across columns `{', '.join(columns)}`."

    @classmethod
    def ask_sql(cls, question: str) -> SQLAskResponse:
        """
        Unified routing entrypoint for natural language questions.
        Routing Policy:
        - Intent confidence >= 0.80 -> Intent router (deterministic validated views).
        - Otherwise -> Guarded Text-to-SQL (dynamic queries).
        """
        start_time = time.time()
        client = AIService._get_genai_client()

        # Step 1: Intent classification check
        if client:
            classification = AIService.classify_intent_gemini(client, question)
        else:
            classification = AIService.classify_intent_heuristic(question)

        intent = classification.get("intent", "unknown")
        confidence = float(classification.get("confidence", 0.0))

        # Check routing policy: intent confidence >= 0.80 routes to intent router
        if confidence >= 0.80 and intent in SUPPORTED_INTENTS:
            try:
                evidence_dict = AIAnalyticsRouter.route_intent(intent)
                answer = AIService.synthesize_explanation_heuristic(question, evidence_dict)
                latency_ms = (time.time() - start_time) * 1000.0

                AIAuditService.log(
                    question=question,
                    intent=intent,
                    generated_sql=None,
                    latency_ms=latency_ms,
                    success=True,
                    error=None
                )

                data = evidence_dict.get("data")
                rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
                cols = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []

                return SQLAskResponse(
                    question=question,
                    route="intent",
                    sql=None,
                    explanation=answer,
                    assumptions=[f"Routed via canonical analytics layer ({intent}) with {confidence:.0%} confidence."],
                    rows=rows[:500],
                    columns=cols,
                    row_count=len(rows),
                    grounding_verified=True,
                    suggested_chart="bar" if len(rows) > 1 else "table",
                    error=None
                )
            except DatabaseUnavailableError:
                raise
            except Exception as e:
                logger.warning(f"Intent routing failed: {e}. Falling back to Text-to-SQL.")

        # Step 2: Route to Guarded Text-to-SQL
        if not client:
            # Cannot do Text-to-SQL without Gemini API Key
            latency_ms = (time.time() - start_time) * 1000.0
            err_msg = "Gemini API key is not configured. Text-to-SQL dynamic generation requires GEMINI_API_KEY."
            AIAuditService.log(
                question=question,
                intent="text_to_sql",
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=err_msg
            )
            return SQLAskResponse(
                question=question,
                route="text_to_sql",
                sql=None,
                explanation=err_msg,
                assumptions=[],
                rows=[],
                columns=[],
                row_count=0,
                grounding_verified=True,
                suggested_chart="table",
                error=err_msg
            )

        gen_result = cls.generate_and_validate_sql(client, question)
        latency_ms = (time.time() - start_time) * 1000.0

        if not gen_result["success"]:
            AIAuditService.log(
                question=question,
                intent="text_to_sql",
                generated_sql=gen_result.get("sql"),
                latency_ms=latency_ms,
                success=False,
                error=gen_result.get("error")
            )
            return SQLAskResponse(
                question=question,
                route="text_to_sql",
                sql=gen_result.get("sql"),
                explanation="I could not safely generate an authorized SQL query for your question. Please try rephrasing with specific metrics or tables.",
                assumptions=[],
                rows=[],
                columns=[],
                row_count=0,
                grounding_verified=True,
                suggested_chart="table",
                error=gen_result.get("error")
            )

        # Grounding verification on explanation against row results
        rows = gen_result["rows"]
        explanation = gen_result["explanation"]
        is_grounded = verify_numeric_grounding(explanation, rows)

        if not is_grounded:
            logger.warning("LLM SQL explanation failed numeric grounding. Generating grounded heuristic summary.")
            explanation = cls.synthesize_fallback_explanation(rows, gen_result["columns"])

        AIAuditService.log(
            question=question,
            intent="text_to_sql",
            generated_sql=gen_result["sql"],
            latency_ms=latency_ms,
            success=True,
            error=None
        )

        return SQLAskResponse(
            question=question,
            route="text_to_sql",
            sql=gen_result["sql"],
            explanation=explanation,
            assumptions=gen_result.get("assumptions", []),
            rows=rows,
            columns=gen_result["columns"],
            row_count=len(rows),
            grounding_verified=is_grounded,
            suggested_chart=gen_result.get("suggested_chart", "table"),
            error=None
        )
