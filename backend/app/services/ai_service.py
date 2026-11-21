import os
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.config import settings
from backend.app.schemas.ai import AskAIResponse, AIEvidence
from backend.app.services.ai_analytics_router import AIAnalyticsRouter, SUPPORTED_INTENTS
from backend.app.services.grounding import verify_numeric_grounding
from backend.app.services.audit_service import AIAuditService

logger = logging.getLogger(__name__)

# Try importing official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai SDK not available in environment.")


class AIService:
    """
    AI Service for InsightForge "Ask InsightForge" feature.
    - Classifies natural-language questions into controlled intents.
    - Routes intent to trusted analytics functions.
    - Synthesizes grounded natural language explanations based ONLY on analytics evidence.
    - LLM never accesses PostgreSQL directly.
    """

    @classmethod
    def _get_genai_client(cls) -> Optional[Any]:
        if not GENAI_AVAILABLE:
            return None
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None
        try:
            return genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Google GenAI client: {e}")
            return None

    @classmethod
    def load_semantic_context(cls) -> str:
        """
        Loads semantic layer definitions (metrics, glossary, dimensions) to provide
        domain awareness for the LLM.
        """
        semantic_dir = BASE_DIR / "semantic"
        context_parts = []

        # Load metrics.yaml
        metrics_file = semantic_dir / "metrics.yaml"
        if metrics_file.exists():
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        metrics_summary = [
                            f"- {k}: {v.get('metric_name', k)} ({v.get('description', '')})"
                            for k, v in data.items() if isinstance(v, dict)
                        ]
                        context_parts.append("METRIC DEFINITIONS:\n" + "\n".join(metrics_summary))
            except Exception as e:
                logger.warning(f"Failed to read metrics.yaml: {e}")

        # Load business_glossary.yaml (top-level keys, not a "glossary" list)
        glossary_file = semantic_dir / "business_glossary.yaml"
        if glossary_file.exists():
            try:
                with open(glossary_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        glossary_summary = []
                        for key, val in data.items():
                            if isinstance(val, dict):
                                name = val.get("name", key)
                                definition = val.get("definition", "")
                                synonyms = val.get("synonyms", [])
                                syn_str = f" (synonyms: {', '.join(synonyms)})" if synonyms else ""
                                glossary_summary.append(f"- {name}: {definition}{syn_str}")
                        context_parts.append("BUSINESS GLOSSARY:\n" + "\n".join(glossary_summary))
            except Exception as e:
                logger.warning(f"Failed to read business_glossary.yaml: {e}")

        return "\n\n".join(context_parts) if context_parts else "InsightForge E-Commerce Analytics Domain."

    @classmethod
    def _wb(cls, pattern: str, text: str) -> bool:
        """Check if pattern matches as a whole word (word-boundary) in text."""
        return bool(re.search(r'\b' + re.escape(pattern) + r'\b', text))

    @classmethod
    def classify_intent_heuristic(cls, question: str) -> Dict[str, Any]:
        """
        Rule-based intent classifier used when Gemini API key is unavailable or offline.
        Maps keywords deterministically to supported intents using word-boundary matching.
        """
        q = question.lower()

        if any(cls._wb(w, q) for w in ["category", "categories", "product category", "highest revenue category"]):
            return {"intent": "category_analysis", "confidence": 0.95, "reason": "Question asks for category sales or revenue ranking."}
        if any(cls._wb(w, q) for w in ["state", "states", "region", "regional", "geographic", "highest sales state"]):
            return {"intent": "state_analysis", "confidence": 0.95, "reason": "Question asks about sales breakdown across customer states."}
        if any(cls._wb(w, q) for w in ["seller", "sellers", "merchant", "merchants", "vendor", "vendors", "top seller"]):
            return {"intent": "seller_analysis", "confidence": 0.95, "reason": "Question requests seller fulfillment or seller performance."}
        if any(cls._wb(w, q) for w in ["delivery", "shipping", "sla", "days to deliver", "delivery performance", "delay", "transit"]):
            return {"intent": "delivery_analysis", "confidence": 0.95, "reason": "Question inquires about delivery performance or SLA timelines."}
        if any(cls._wb(w, q) for w in ["payment", "payment method", "credit card", "boleto", "installments", "voucher", "debit"]):
            return {"intent": "payment_analysis", "confidence": 0.95, "reason": "Question focuses on payment methods or payment amounts."}
        if any(cls._wb(w, q) for w in ["trend", "monthly", "month over month", "mom", "revenue growth", "over time", "trajectory", "seasonal"]):
            return {"intent": "revenue_trend", "confidence": 0.95, "reason": "Question inquires about monthly revenue or order trends."}
        if any(cls._wb(w, q) for w in ["data quality", "audit", "null", "missing", "integrity", "duplicate", "row count", "domain bounds"]):
            return {"intent": "data_quality", "confidence": 0.95, "reason": "Question asks about database quality, nulls, or table audits."}
        if any(cls._wb(w, q) for w in ["kpi", "kpis", "aov", "average order value", "csat", "overview", "summary", "total revenue", "gross revenue", "product revenue", "delivered orders", "total orders", "active customer", "performance", "overall"]):
            return {"intent": "kpi_summary", "confidence": 0.95, "reason": "Question requests general high-level KPI summary metrics."}

        return {"intent": "unknown", "confidence": 0.30, "reason": "Could not confidently match question to supported business intents."}

    @classmethod
    def classify_intent_gemini(cls, client: Any, question: str) -> Dict[str, Any]:
        """
        Classifies user question into supported intent using Gemini API with structured JSON output.
        """
        prompt = f"""
You are an intent classification system for InsightForge business intelligence platform.
Classify the user's natural language question into EXACTLY ONE of the supported business intents listed below.

SUPPORTED INTENTS:
1. kpi_summary - High level executive KPIs (Gross revenue, product revenue, freight revenue, delivered orders, active customers, units sold, AOV, CSAT).
2. revenue_trend - Monthly sales performance, order counts, MoM growth trends.
3. category_analysis - Top product categories, category revenue share, average item price, review score.
4. state_analysis - Geographic breakdown by customer state, regional revenue, active customers by state.
5. seller_analysis - Top performing sellers, orders fulfilled, units sold, seller revenue, seller ratings.
6. payment_analysis - Payment method distribution (credit card, boleto, voucher, debit), average installments, payment value.
7. delivery_analysis - Delivery SLA performance, actual delivery days vs estimated days, delay status breakdown.
8. data_quality - Data quality audit, row counts, missing values, primary/foreign key checks, join safety.

If the question is completely unrelated to business intelligence, e-commerce, or these domains, set intent to "unknown" and confidence below 0.50.

Respond strictly in valid JSON format:
{{
    "intent": "<one of the 8 supported intents or unknown>",
    "confidence": <float between 0.0 and 1.0>,
    "reason": "<short explanation>"
}}

User Question: "{question}"
"""
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=config
            )
            raw_text = response.text.strip()
            parsed = json.loads(raw_text)

            intent = parsed.get("intent", "unknown")
            confidence = float(parsed.get("confidence", 0.0))
            reason = parsed.get("reason", "Gemini intent classification.")

            # Bounds check confidence
            confidence = max(0.0, min(1.0, confidence))

            if intent not in SUPPORTED_INTENTS:
                intent = "unknown"

            return {"intent": intent, "confidence": confidence, "reason": reason}

        except Exception as e:
            logger.error(f"Gemini classification failed: {e}. Falling back to heuristic classifier.")
            return cls.classify_intent_heuristic(question)

    @classmethod
    def synthesize_explanation_heuristic(cls, question: str, evidence: Dict[str, Any]) -> str:
        """
        Generates a clear, grounded explanation when Gemini API is offline or not configured.
        """
        intent = evidence.get("intent")
        data = evidence.get("data")

        if intent == "category_analysis" and isinstance(data, list) and len(data) > 0:
            top = data[0]
            cat_name = (top.get("product_category_name_english") or top.get("category") or "Unknown category").replace("_", " ").title()
            rev = top.get("total_revenue", 0)
            share = top.get("revenue_contribution_pct") or top.get("revenue_share_percent", 0)
            orders = top.get("units_sold") or top.get("total_orders", 0)
            return (
                f"Based on PostgreSQL analytics, the product category generating the highest revenue is **{cat_name}** "
                f"with **R$ {rev:,.2f}** in total revenue ({share:.2f}% of total revenue across {orders:,} orders). "
                f"The top 3 categories overall are {', '.join([(d.get('product_category_name_english') or d.get('category') or '').replace('_', ' ').title() for d in data[:3]])}."
            )

        elif intent == "kpi_summary" and isinstance(data, dict):
            gross = data.get("total_gross_revenue") or data.get("gross_revenue", 0)
            prod = data.get("total_product_revenue") or data.get("product_revenue", 0)
            freight = data.get("total_freight_revenue") or data.get("freight_revenue", 0)
            orders = data.get("total_delivered_orders") or data.get("delivered_orders", 0)
            aov = data.get("aov", 0)
            csat = data.get("avg_review_score") or data.get("csat", 0)
            return (
                f"Here is our executive KPI summary from validated PostgreSQL records:\n"
                f"• **Gross Revenue**: R$ {gross:,.2f} (Product: R$ {prod:,.2f}, Freight: R$ {freight:,.2f})\n"
                f"• **Delivered Orders**: {orders:,} completed orders\n"
                f"• **Average Order Value (AOV)**: R$ {aov:,.2f}\n"
                f"• **Customer Satisfaction (CSAT)**: {csat:.2f} / 5.0"
            )

        elif intent == "state_analysis" and isinstance(data, list) and len(data) > 0:
            top_state = data[0]
            st = top_state.get("customer_state") or top_state.get("state", "SP")
            rev = top_state.get("total_revenue") or top_state.get("total_gross_revenue", 0)
            share = top_state.get("revenue_contribution_pct") or top_state.get("revenue_share_percent", 0)
            cust = top_state.get("delivered_orders") or top_state.get("active_customers", 0)
            return (
                f"Customer state **{st}** generates the highest sales volume, contributing **R$ {rev:,.2f}** "
                f"({share:.2f}% of total gross revenue) from {cust:,} active purchasing customers."
            )

        elif intent == "delivery_analysis":
            if isinstance(data, dict):
                on_time_pct = data.get("on_time_delivery_pct", 0)
                avg_days = data.get("avg_delivery_duration_days", 0)
                delay_pct = 100.0 - on_time_pct if on_time_pct > 0 else 0
                return (
                    f"Delivery SLA analytics show that **{on_time_pct:.1f}%** of orders were delivered on time "
                    f"with an average delivery timeframe of {avg_days:.1f} days. "
                    f"Delayed deliveries account for {delay_pct:.1f}% of total shipments."
                )
            elif isinstance(data, list) and len(data) > 0:
                on_time = next((d for d in data if d.get("delivery_status") == "On-Time"), {})
                delayed = next((d for d in data if d.get("delivery_status") == "Delayed"), {})
                on_time_pct = on_time.get("percentage", 0)
                avg_days = on_time.get("avg_actual_delivery_days", 0)
                return (
                    f"Delivery SLA analytics show that **{on_time_pct:.1f}%** of orders were delivered on time "
                    f"with an average delivery timeframe of {avg_days:.1f} days. "
                    f"Delayed deliveries account for {delayed.get('percentage', 0):.1f}% of total shipments."
                )

        elif intent == "payment_analysis" and isinstance(data, list) and len(data) > 0:
            top_pay = data[0]
            p_type = top_pay.get("payment_type", "credit_card").replace("_", " ").title()
            p_count = top_pay.get("order_count", 0)
            p_val = top_pay.get("total_payment_value", 0)
            return (
                f"The most common payment method is **{p_type}**, used in {p_count:,} orders "
                f"totaling **R$ {p_val:,.2f}** in transaction value."
            )

        elif intent == "revenue_trend" and isinstance(data, list) and len(data) > 0:
            latest = data[-1]
            m = latest.get("year_month") or latest.get("month", "")
            rev = latest.get("gross_revenue", 0)
            orders = latest.get("delivered_order_count") or latest.get("total_orders", 0)
            return (
                f"Monthly revenue trend analytics cover {len(data)} consecutive months. "
                f"In the most recent recorded month ({m}), total gross revenue reached **R$ {rev:,.2f}** "
                f"across {orders:,} fulfilled orders."
            )

        elif intent == "seller_analysis" and isinstance(data, list) and len(data) > 0:
            top_s = data[0]
            s_id = top_s.get("seller_id", "")[:8]
            s_rev = top_s.get("total_revenue") or top_s.get("total_sales_revenue", 0)
            s_orders = top_s.get("units_sold") or top_s.get("total_orders_fulfilled", 0)
            return (
                f"Top seller (ID prefix: `{s_id}...`) generated **R$ {s_rev:,.2f}** in sales revenue "
                f"fulfilling {s_orders:,} customer orders."
            )

        elif intent == "data_quality" and isinstance(data, dict):
            status = data.get("audit_status", "PASS")
            tables = len(data.get("table_row_counts", {})) if "table_row_counts" in data else 7
            pk = data.get("primary_key_uniqueness", "PASS")
            fk = data.get("foreign_key_integrity", "PASS")
            return (
                f"Data quality audit status is **{status}**. Verified {tables} core database tables. "
                f"Primary key uniqueness check: {pk}. Foreign key integrity check: {fk}."
            )

        return f"Analytics query for intent '{intent}' executed successfully against PostgreSQL. Evidence data loaded."

    @classmethod
    def synthesize_explanation_gemini(cls, client: Any, question: str, evidence: Dict[str, Any]) -> str:
        """
        Synthesizes grounded explanation using Gemini API based strictly on provided evidence.
        """
        semantic_context = cls.load_semantic_context()
        data_json = json.dumps(evidence.get("data"), indent=2, default=str)

        prompt = f"""
You are InsightForge's grounded AI Business Analyst.
Your task is to answer the user's question using ONLY the provided PostgreSQL analytics evidence below.

CRITICAL RULES FOR GROUNDED SYNTHESIS:
1. Use ONLY the supplied evidence payload.
2. Do NOT invent numbers, percentages, dates, or non-existent metrics.
3. Do NOT claim causality unless the evidence explicitly proves it.
4. If the evidence is insufficient to answer a specific part of the question, state that clearly.
5. Distinguish contribution/correlation from causation.
6. Present the output in concise, professional business-oriented Markdown (formatted nicely with bolding and bullet points where helpful). Keep it around 3 to 5 sentences or concise bullet points.

{semantic_context}

EVIDENCE PAYLOAD:
- Source: {evidence.get("source")}
- Intent: {evidence.get("intent")}
- Primary Metric: {evidence.get("metric")}
- Validated PostgreSQL Data:
{data_json}

User Question: "{question}"
"""
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt
            )
            answer = response.text.strip()
            if answer:
                return answer
        except Exception as e:
            logger.error(f"Gemini synthesis failed: {e}. Falling back to heuristic synthesis.")

        return cls.synthesize_explanation_heuristic(question, evidence)

    @classmethod
    def ask(cls, question: str) -> AskAIResponse:
        """
        Main entry point for "Ask InsightForge".
        1. Classifies intent (Gemini if API key configured, otherwise rule-based fallback).
        2. Validates confidence (>= 0.60) and intent allow-list.
        3. Routes to analytics function if confident.
        4. Synthesizes grounded explanation.
        5. Returns structured response.
        """
        start_time = time.time()
        client = cls._get_genai_client()

        # 1. Classification
        if client:
            classification = cls.classify_intent_gemini(client, question)
        else:
            classification = cls.classify_intent_heuristic(question)

        intent = classification["intent"]
        confidence = classification["confidence"]
        reason = classification["reason"]

        # 2. Check confidence threshold (0.60) and intent allow-list
        if confidence < 0.60 or intent not in SUPPORTED_INTENTS:
            latency_ms = (time.time() - start_time) * 1000.0
            AIAuditService.log(
                question=question,
                intent=intent if intent in SUPPORTED_INTENTS else "unknown",
                generated_sql=None,
                latency_ms=latency_ms,
                success=True,
                error=None
            )
            return AskAIResponse(
                question=question,
                intent=intent if intent in SUPPORTED_INTENTS else "unknown",
                confidence=confidence,
                reason=reason,
                answer=(
                    "I'm sorry, I couldn't confidently map your question to our available business analytics. "
                    "Please rephrase your question to focus on one of our supported topics: "
                    "product category revenue, monthly revenue trends, customer state sales, top sellers, "
                    "delivery performance, payment breakdown, executive KPIs, or data quality audits."
                ),
                evidence=None,
                rephrase_suggested=True,
                grounding_verified=True
            )

        # 3. Route to existing validated analytics function
        try:
            evidence_dict = AIAnalyticsRouter.route_intent(intent)
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            logger.error(f"Error routing intent '{intent}': {e}")
            AIAuditService.log(
                question=question,
                intent=intent,
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
            return AskAIResponse(
                question=question,
                intent=intent,
                confidence=confidence,
                reason=f"Analytics routing failed: {str(e)}",
                answer="An error occurred while retrieving data from PostgreSQL analytics. Please try again later.",
                evidence=None,
                rephrase_suggested=False,
                grounding_verified=True
            )

        # 4. Synthesize explanation & verify numeric grounding
        grounding_verified = True
        if client:
            llm_answer = cls.synthesize_explanation_gemini(client, question, evidence_dict)
            # Run numeric faithfulness verifier
            if verify_numeric_grounding(llm_answer, evidence_dict["data"]):
                answer = llm_answer
                grounding_verified = True
            else:
                logger.warning(
                    f"LLM answer failed numeric verification. Falling back to heuristic synthesis for question: '{question}'"
                )
                answer = cls.synthesize_explanation_heuristic(question, evidence_dict)
                grounding_verified = False
        else:
            answer = cls.synthesize_explanation_heuristic(question, evidence_dict)
            grounding_verified = True

        evidence_obj = AIEvidence(
            source=evidence_dict["source"],
            intent=evidence_dict["intent"],
            metric=evidence_dict["metric"],
            data=evidence_dict["data"]
        )

        latency_ms = (time.time() - start_time) * 1000.0
        AIAuditService.log(
            question=question,
            intent=intent,
            generated_sql=None,
            latency_ms=latency_ms,
            success=True,
            error=None
        )

        return AskAIResponse(
            question=question,
            intent=intent,
            confidence=confidence,
            reason=reason,
            answer=answer,
            evidence=evidence_obj,
            rephrase_suggested=False,
            grounding_verified=grounding_verified
        )
