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
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError
from backend.app.fixture_guard import assert_database_available, is_fixture_mode_allowed

logger = logging.getLogger(__name__)

# Try importing official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google-genai SDK not available in environment.")


def detect_language(text: str) -> str:
    """
    Detects whether the question is in Hindi (Devanagari), Hinglish (Roman script), or English.
    """
    if not text:
        return "en"
    # Devanagari Unicode Block U+0900 to U+097F
    if re.search(r'[\u0900-\u097F]', text):
        return "hi"

    # Distinctive Hinglish vocabulary / grammar tokens
    hinglish_markers = {
        "sabse", "zyada", "jyada", "bikri", "munafa", "kaunsa", "kaunsi",
        "kaunse", "kitna", "kitne", "kitni", "hai", "hain", "kya", "mein",
        "batao", "dikhao", "rajya", "vikreta", "bhugtan", "varg", "shreni",
        "samay", "deri", "mahine", "anusaar", "mutabiq", "karo", "aaye", "gaye",
        "hazar", "hazaar", "lakh", "crore"
    }
    tokens = set(re.findall(r'[a-zA-Z]+', text.lower()))
    if len(tokens.intersection(hinglish_markers)) >= 1:
        return "hinglish"
    return "en"


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
        # For non-ASCII (e.g. Devanagari) or phrases with spaces, use boundary or whitespace check
        if re.search(r'[\u0900-\u097F]', pattern) or ' ' in pattern:
            return bool(re.search(r'(?:\b|^|\s)' + re.escape(pattern) + r'(?:\b|$|\s|[?.,!])', text, re.IGNORECASE))
        return bool(re.search(r'\b' + re.escape(pattern) + r'\b', text, re.IGNORECASE))

    @classmethod
    def classify_intent_heuristic(cls, question: str) -> Dict[str, Any]:
        """
        Rule-based intent classifier supporting English, Hindi (Devanagari), and Hinglish.
        Used when Gemini API key is unavailable or offline.
        Maps keywords deterministically to supported intents using word-boundary matching.
        """
        q = question.lower()

        # 1. Anomaly Detection
        if any(cls._wb(w, q) for w in [
            "anomaly", "anomalies", "outlier", "outliers", "unusual", "spike", "spikes", "surge",
            "surges", "abnormal", "irregular", "irregularity", "irregularities", "dip", "dips",
            "unexpected peak", "black friday", "विसंगति", "विसंगतियां", "विसंगतियों", "असामान्य",
            "असाधारण", "उछाल", "गिरावट", "स्पाइक", "ब्लैक फ्राइडे", "आउटलायर", "visangati",
            "asamanya", "uchhal", "giravat"
        ]):
            return {"intent": "anomaly_detection", "confidence": 0.95, "reason": "Question inquires about statistical anomalies, spikes, dips, or outliers."}

        # 2. State / Regional Analysis (Check before category so 'highest sales state' / 'किस राज्य से बिक्री' matches state)
        if any(cls._wb(w, q) for w in [
            "state", "states", "region", "regional", "geographic", "highest sales state",
            "राज्य", "राज्यों", "प्रांत", "क्षेत्रीय", "क्षेत्र", "साओ पाउलो",
            "rajya", "rajyo", "prant", "kshetra", "kshetriy", "sao paulo"
        ]):
            return {"intent": "state_analysis", "confidence": 0.95, "reason": "Question asks about sales breakdown across customer states."}

        # 3. Seller Analysis (Check before generic sales terms)
        if any(cls._wb(w, q) for w in [
            "seller", "sellers", "merchant", "merchants", "vendor", "vendors", "top seller",
            "विक्रेता", "विक्रेताओं", "व्यापारी", "मर्चेंट", "सेलर", "सर्वश्रेष्ठ विक्रेता",
            "vikreta", "vikretaon", "vyapari", "top merchant"
        ]):
            return {"intent": "seller_analysis", "confidence": 0.95, "reason": "Question requests seller fulfillment or seller performance."}

        # 4. Category Analysis
        if any(cls._wb(w, q) for w in [
            "category", "categories", "product category", "highest revenue category",
            "श्रेणी", "श्रेणियों", "कैटेगरी", "वर्ग", "उत्पाद श्रेणी", "सर्वाधिक बिक्री",
            "सबसे ज्यादा बिक्री", "सबसे कम बिक्री", "shreni", "varg", "sabse zyada bikri",
            "sabse jyada bikri", "sabse adhik bikri", "sabse kam bikri"
        ]):
            return {"intent": "category_analysis", "confidence": 0.95, "reason": "Question asks for category sales or revenue ranking."}

        # 5. Delivery SLA
        if any(cls._wb(w, q) for w in [
            "delivery", "shipping", "sla", "days to deliver", "delivery performance", "delay", "transit",
            "डिलीवरी", "वितरण", "समय पर", "समय पर डिलीवरी", "विलंब", "देरी", "शिपिंग", "एसएलए",
            "vitran", "samay par", "vilamb", "deri", "late delivery"
        ]):
            return {"intent": "delivery_analysis", "confidence": 0.95, "reason": "Question inquires about delivery performance or SLA timelines."}

        # 6. Payment Analysis
        if any(cls._wb(w, q) for w in [
            "payment", "payment method", "credit card", "boleto", "installments", "voucher", "debit",
            "भुगतान", "पेमेंट", "भुगतान विधि", "क्रेडिट कार्ड", "बोलेतो", "किस्त", "किस्तें", "वाउचर", "डेबिट",
            "bhugtan", "kist", "kisten", "installments", "voucher"
        ]):
            return {"intent": "payment_analysis", "confidence": 0.95, "reason": "Question focuses on payment methods or payment amounts."}

        # 7. Revenue Trend
        if any(cls._wb(w, q) for w in [
            "trend", "monthly", "month", "months", "month over month", "mom", "revenue growth", "over time", "trajectory", "seasonal",
            "peak month", "peak sales", "highest month", "lowest month", "peak aaya",
            "रुझान", "मासिक", "माह", "महीना", "महीने", "मासिक वृद्धि", "महीने दर महीने", "बिक्री रुझान", "शीर्ष महीना",
            "masik", "mahina", "mahine", "mahine dar mahine", "sales trend", "growth rate", "peak", "kaun se mahine"
        ]):
            return {"intent": "revenue_trend", "confidence": 0.95, "reason": "Question inquires about monthly revenue or order trends."}

        # 8. Data Quality
        if any(cls._wb(w, q) for w in [
            "data quality", "audit", "null", "missing", "integrity", "duplicate", "row count", "domain bounds",
            "डेटा गुणवत्ता", "गुणवत्ता", "जांच", "ऑडिट", "डुप्लिकेट", "नल", "अखंडता",
            "gunvatta", "janch", "data audit"
        ]):
            return {"intent": "data_quality", "confidence": 0.95, "reason": "Question asks about database quality, nulls, or table audits."}

        # 9. Executive KPI Summary
        if any(cls._wb(w, q) for w in [
            "kpi", "kpis", "aov", "average order value", "csat", "overview", "summary", "total revenue",
            "gross revenue", "product revenue", "delivered orders", "delivered order", "total orders", "active customer",
            "active customers", "performance", "overall", "kul rajasva", "sakal rajasva", "munafa",
            "kul bikri", "कुल राजस्व", "सकल राजस्व", "उत्पाद राजस्व", "कुल बिक्री", "मुनाफा",
            "औसत ऑर्डर मूल्य", "ग्राहक संतुष्टि", "केपीआई", "संक्षिप्त विवरण", "कार्यकारी सारांश", "bikri",
            "कुल कितने ऑर्डर", "कितने ऑर्डर", "कुल ऑर्डर", "सफलतापूर्वक डिलीवर", "सफलतापूर्वक डिलीवरी"
        ]):
            return {"intent": "kpi_summary", "confidence": 0.95, "reason": "Question requests general high-level KPI summary metrics."}

        return {"intent": "unknown", "confidence": 0.30, "reason": "Could not confidently match question to supported business intents."}

    @classmethod
    def classify_intent_gemini(cls, client: Any, question: str, raise_on_error: bool = False) -> Dict[str, Any]:
        """
        Classifies user question into supported intent using Gemini API with structured JSON output.
        Accepts questions in English, Hindi (Devanagari), or Hinglish.
        """
        lang = detect_language(question)
        prompt = f"""
You are an intent classification system for InsightForge business intelligence platform.
Classify the user's natural language question into EXACTLY ONE of the supported business intents listed below.
The question may be asked in English, Hindi (Devanagari script), or Hinglish (Hindi in Roman script). Always classify correctly regardless of the language.

SUPPORTED INTENTS:
1. kpi_summary - High level executive KPIs (Gross revenue, product revenue, freight revenue, delivered orders, active customers, units sold, AOV, CSAT).
2. revenue_trend - Monthly sales performance, order counts, MoM growth trends.
3. category_analysis - Top product categories, category revenue share, average item price, review score.
4. state_analysis - Geographic breakdown by customer state, regional revenue, active customers by state.
5. seller_analysis - Top performing sellers, orders fulfilled, units sold, seller revenue, seller ratings.
6. payment_analysis - Payment method distribution (credit card, boleto, voucher, debit), average installments, payment value.
7. delivery_analysis - Delivery SLA performance, actual delivery days vs estimated days, delay status breakdown.
8. data_quality - Data quality audit, row counts, missing values, primary/foreign key checks, join safety.
9. anomaly_detection - Statistical anomalies, sales spikes, unusual drops, outliers, abnormal variations, seasonal events (Black Friday).

If the question is completely unrelated to business intelligence, e-commerce, or these domains, set intent to "unknown" and confidence below 0.50.

Respond strictly in valid JSON format:
{{
    "intent": "<one of the 9 supported intents or unknown>",
    "confidence": <float between 0.0 and 1.0>,
    "reason": "<short explanation>",
    "language": "en" | "hi" | "hinglish"
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
            res_lang = parsed.get("language") or lang

            # Bounds check confidence
            confidence = max(0.0, min(1.0, confidence))

            if intent not in SUPPORTED_INTENTS:
                intent = "unknown"

            return {"intent": intent, "confidence": confidence, "reason": reason, "language": res_lang}

        except Exception as e:
            if raise_on_error:
                raise
            logger.error(f"Gemini classification failed: {e}. Falling back to heuristic classifier.")
            res = cls.classify_intent_heuristic(question)
            res["language"] = lang
            return res

    @classmethod
    def synthesize_explanation_heuristic(cls, question: str, evidence: Dict[str, Any], language: Optional[str] = None) -> str:
        """
        Generates a clear, grounded explanation when Gemini API is offline or not configured.
        Supports English, Hindi (Devanagari), and Hinglish (Roman script) with Western digits 0-9.
        """
        if language is None:
            language = detect_language(question)

        intent = evidence.get("intent")
        data = evidence.get("data")

        # ------------------------------------------------------------------
        # Category Analysis
        # ------------------------------------------------------------------
        if intent == "category_analysis" and isinstance(data, list) and len(data) > 0:
            top = data[0]
            cat_name = (top.get("product_category_name_english") or top.get("category") or "Unknown category").replace("_", " ").title()
            rev = top.get("total_revenue", 0)
            share = top.get("revenue_contribution_pct") or top.get("revenue_share_percent", 0)
            orders = top.get("units_sold") or top.get("total_orders", 0)

            if language == "hi":
                return (
                    f"PostgreSQL एनालिटिक्स के अनुसार, सबसे अधिक राजस्व उत्पन्न करने वाली उत्पाद श्रेणी **{cat_name}** है, "
                    f"जिसका कुल राजस्व **R$ {rev:,.2f}** ({share:.2f}% हिस्सा) रहा। कुल {orders:,} यूनिट्स बेची गईं।"
                )
            elif language == "hinglish":
                return (
                    f"PostgreSQL analytics ke mutabiq, sabse zyada revenue generate karne wali product category **{cat_name}** hai, "
                    f"jiska total revenue **R$ {rev:,.2f}** ({share:.2f}% contribution) raha across {orders:,} units."
                )
            else:
                return (
                    f"Based on PostgreSQL analytics, the product category generating the highest revenue is **{cat_name}** "
                    f"with **R$ {rev:,.2f}** in total revenue ({share:.2f}% of total revenue across {orders:,} orders). "
                    f"The top 3 categories overall are {', '.join([(d.get('product_category_name_english') or d.get('category') or '').replace('_', ' ').title() for d in data[:3]])}."
                )

        # ------------------------------------------------------------------
        # Executive KPI Summary
        # ------------------------------------------------------------------
        elif intent == "kpi_summary" and isinstance(data, dict):
            gross = data.get("total_gross_revenue") or data.get("gross_revenue", 0)
            prod = data.get("total_product_revenue") or data.get("product_revenue", 0)
            freight = data.get("total_freight_revenue") or data.get("freight_revenue", 0)
            orders = data.get("total_delivered_orders") or data.get("delivered_orders", 0)
            aov = data.get("aov", 0)
            csat = data.get("avg_review_score") or data.get("csat", 0)

            if language == "hi":
                return (
                    f"सत्यापित PostgreSQL रिकॉर्ड्स से हमारा कार्यकारी केपीआई (KPI) सारांश:\n"
                    f"• **कुल सकल राजस्व (Gross Revenue)**: R$ {gross:,.2f} (उत्पाद: R$ {prod:,.2f}, फ्रेट: R$ {freight:,.2f})\n"
                    f"• **डिलीवर किए गए कुल ऑर्डर**: {orders:,}\n"
                    f"• **औसत ऑर्डर मूल्य (AOV)**: R$ {aov:,.2f}\n"
                    f"• **ग्राहक संतुष्टि (CSAT)**: {csat:.2f} / 5.0"
                )
            elif language == "hinglish":
                return (
                    f"Validated PostgreSQL records ke anusaar executive KPI summary:\n"
                    f"• **Gross Revenue**: R$ {gross:,.2f} (Product: R$ {prod:,.2f}, Freight: R$ {freight:,.2f})\n"
                    f"• **Delivered Orders**: {orders:,} completed orders\n"
                    f"• **Average Order Value (AOV)**: R$ {aov:,.2f}\n"
                    f"• **Customer CSAT**: {csat:.2f} / 5.0"
                )
            else:
                return (
                    f"Here is our executive KPI summary from validated PostgreSQL records:\n"
                    f"• **Gross Revenue**: R$ {gross:,.2f} (Product: R$ {prod:,.2f}, Freight: R$ {freight:,.2f})\n"
                    f"• **Delivered Orders**: {orders:,} completed orders\n"
                    f"• **Average Order Value (AOV)**: R$ {aov:,.2f}\n"
                    f"• **Customer Satisfaction (CSAT)**: {csat:.2f} / 5.0"
                )

        # ------------------------------------------------------------------
        # State / Regional Analysis
        # ------------------------------------------------------------------
        elif intent == "state_analysis" and isinstance(data, list) and len(data) > 0:
            top_state = data[0]
            st = top_state.get("customer_state") or top_state.get("state", "SP")
            rev = top_state.get("total_revenue") or top_state.get("total_gross_revenue", 0)
            share = top_state.get("revenue_contribution_pct") or top_state.get("revenue_share_percent", 0)
            cust = top_state.get("delivered_orders") or top_state.get("active_customers", 0)

            if language == "hi":
                return (
                    f"ग्राहक राज्य **{st}** सबसे अधिक बिक्री उत्पन्न करता है, जिससे **R$ {rev:,.2f}** "
                    f"(कुल सकल राजस्व का {share:.2f}%) प्राप्त हुआ, {cust:,} सक्रिय ग्राहकों के माध्यम से।"
                )
            elif language == "hinglish":
                return (
                    f"Customer state **{st}** sabse zyada sales volume generate karta hai, contributing **R$ {rev:,.2f}** "
                    f"({share:.2f}% of total gross revenue) from {cust:,} active purchasing customers."
                )
            else:
                return (
                    f"Customer state **{st}** generates the highest sales volume, contributing **R$ {rev:,.2f}** "
                    f"({share:.2f}% of total gross revenue) from {cust:,} active purchasing customers."
                )

        # ------------------------------------------------------------------
        # Delivery SLA
        # ------------------------------------------------------------------
        elif intent == "delivery_analysis":
            if isinstance(data, dict):
                on_time_pct = data.get("on_time_delivery_pct", 0)
                avg_days = data.get("avg_delivery_duration_days", 0)
                delay_pct = 100.0 - on_time_pct if on_time_pct > 0 else 0
            elif isinstance(data, list) and len(data) > 0:
                on_time = next((d for d in data if d.get("delivery_status") == "On-Time"), {})
                delayed = next((d for d in data if d.get("delivery_status") == "Delayed"), {})
                on_time_pct = on_time.get("percentage", 0)
                avg_days = on_time.get("avg_actual_delivery_days", 0)
                delay_pct = delayed.get("percentage", 0)
            else:
                on_time_pct, avg_days, delay_pct = 0.0, 0.0, 0.0

            if language == "hi":
                return (
                    f"डिलीवरी एसएलए (SLA) एनालिटिक्स के अनुसार, **{on_time_pct:.1f}%** ऑर्डर समय पर डिलीवर किए गए, "
                    f"जिसमें औसत डिलीवरी समय {avg_days:.1f} दिन रहा। विलंबित डिलीवरी का हिस्सा {delay_pct:.1f}% है।"
                )
            elif language == "hinglish":
                return (
                    f"Delivery SLA analytics ke according, **{on_time_pct:.1f}%** orders time par deliver hue "
                    f"with average delivery timeframe of {avg_days:.1f} days. Delayed deliveries {delay_pct:.1f}% hain."
                )
            else:
                return (
                    f"Delivery SLA analytics show that **{on_time_pct:.1f}%** of orders were delivered on time "
                    f"with an average delivery timeframe of {avg_days:.1f} days. "
                    f"Delayed deliveries account for {delay_pct:.1f}% of total shipments."
                )

        # ------------------------------------------------------------------
        # Payment Analysis
        # ------------------------------------------------------------------
        elif intent == "payment_analysis" and isinstance(data, list) and len(data) > 0:
            top_pay = data[0]
            p_type = top_pay.get("payment_type", "credit_card").replace("_", " ").title()
            p_count = top_pay.get("order_count", 0)
            p_val = top_pay.get("total_payment_value", 0)

            if language == "hi":
                return (
                    f"सबसे आम भुगतान विधि **{p_type}** है, जिसका उपयोग {p_count:,} ऑर्डरों में किया गया, "
                    f"जिसका कुल लेनदेन मूल्य **R$ {p_val:,.2f}** है।"
                )
            elif language == "hinglish":
                return (
                    f"Sabse common payment method **{p_type}** hai, jo {p_count:,} orders mein use hua "
                    f"totaling **R$ {p_val:,.2f}** in transaction value."
                )
            else:
                return (
                    f"The most common payment method is **{p_type}**, used in {p_count:,} orders "
                    f"totaling **R$ {p_val:,.2f}** in transaction value."
                )

        # ------------------------------------------------------------------
        # Revenue Trend
        # ------------------------------------------------------------------
        elif intent == "revenue_trend" and isinstance(data, list) and len(data) > 0:
            latest = data[-1]
            m = latest.get("year_month") or latest.get("month", "")
            rev = latest.get("gross_revenue", 0)
            orders = latest.get("delivered_order_count") or latest.get("total_orders", 0)

            if language == "hi":
                return (
                    f"मासिक बिक्री रुझान के अनुसार, हालिया दर्ज महीने ({m}) में कुल सकल राजस्व **R$ {rev:,.2f}** रहा, "
                    f"जिसमें {orders:,} ऑर्डर पूरे किए गए।"
                )
            elif language == "hinglish":
                return (
                    f"Monthly sales trend ke anusaar, latest recorded month ({m}) mein total gross revenue **R$ {rev:,.2f}** "
                    f"tha across {orders:,} fulfilled orders."
                )
            else:
                return (
                    f"Monthly revenue trend analytics cover consecutive monthly periods. "
                    f"In the most recent recorded month ({m}), total gross revenue reached **R$ {rev:,.2f}** "
                    f"across {orders:,} fulfilled orders."
                )

        # ------------------------------------------------------------------
        # Seller Analysis
        # ------------------------------------------------------------------
        elif intent == "seller_analysis" and isinstance(data, list) and len(data) > 0:
            top_s = data[0]
            s_id = top_s.get("seller_id", "")[:8]
            s_rev = top_s.get("total_revenue") or top_s.get("total_sales_revenue", 0)
            s_orders = top_s.get("units_sold") or top_s.get("total_orders_fulfilled", 0)

            if language == "hi":
                return (
                    f"शीर्ष विक्रेता (ID: `{s_id}...`) ने {s_orders:,} ऑर्डर पूरे करके **R$ {s_rev:,.2f}** "
                    f"का बिक्री राजस्व अर्जित किया।"
                )
            elif language == "hinglish":
                return (
                    f"Top seller (ID: `{s_id}...`) ne **R$ {s_rev:,.2f}** sales revenue generate kiya "
                    f"fulfilling {s_orders:,} customer orders."
                )
            else:
                return (
                    f"Top seller (ID prefix: `{s_id}...`) generated **R$ {s_rev:,.2f}** in sales revenue "
                    f"fulfilling {s_orders:,} customer orders."
                )

        # ------------------------------------------------------------------
        # Data Quality
        # ------------------------------------------------------------------
        elif intent == "data_quality" and isinstance(data, dict):
            status = data.get("audit_status", "PASS")
            tables = len(data.get("table_row_counts", {})) if "table_row_counts" in data else 7
            pk = data.get("primary_key_uniqueness", "PASS")
            fk = data.get("foreign_key_integrity", "PASS")

            if language == "hi":
                return (
                    f"डेटा गुणवत्ता ऑडिट की स्थिति **{status}** है। {tables} मुख्य डेटाबेस तालिकाओं का सत्यापन किया गया। "
                    f"प्राथमिक कुंजी विशिष्टता: {pk}। विदेशी कुंजी अखंडता: {fk}।"
                )
            elif language == "hinglish":
                return (
                    f"Data quality audit status **{status}** hai across {tables} core database tables. "
                    f"Primary key check: {pk}, Foreign key integrity: {fk}."
                )
            else:
                return (
                    f"Data quality audit status is **{status}**. Verified {tables} core database tables. "
                    f"Primary key uniqueness check: {pk}. Foreign key integrity check: {fk}."
                )

        # ------------------------------------------------------------------
        # Anomaly Detection
        # ------------------------------------------------------------------
        elif intent == "anomaly_detection":
            if isinstance(data, dict):
                total = data.get("total_anomalies", 0)
                high_count = data.get("high_severity_count", 0)
                metric_counts = data.get("metric_counts", {})
                top_items = data.get("top_anomalies", [])
            elif isinstance(data, list):
                total = len(data)
                high_count = sum(1 for a in data if a.get("severity") == "high")
                metric_counts = {}
                top_items = data
            else:
                total = 0
                high_count = 0
                metric_counts = {}
                top_items = []

            counts_breakdown = ", ".join([f"{k.replace('_', ' ').title()}: {v}" for k, v in sorted(metric_counts.items())]) if metric_counts else ""

            top_events_formatted = []
            for idx, a in enumerate(top_items[:3], 1):
                p = a.get("period", "")
                m = (a.get("metric") or "metric").replace("_", " ")
                obs = a.get("observed", 0.0)
                exp = a.get("expected", 0.0)
                ev = a.get("known_event_candidate")
                ev_str = f" [{ev}]" if ev else " [statistical_outlier]"
                obs_fmt = f"R$ {obs:,.2f}" if "revenue" in m or "aov" in m else f"{obs:,.2f}"
                exp_fmt = f"R$ {exp:,.2f}" if "revenue" in m or "aov" in m else f"{exp:,.2f}"
                top_events_formatted.append(f"{idx}. {p} ({m}): observed {obs_fmt} vs expected {exp_fmt}{ev_str}")

            events_bullet = "\n• " + "\n• ".join(top_events_formatted) if top_events_formatted else ""

            if language == "hi":
                return (
                    f"दैनिक बहु-मैट्रिक विसंगति जांच (राजस्व, ऑर्डर, एओवी, वितरण एसएलए और सीएसएटी) के दायरे में कुल **{total}** सांख्यिकीय विसंगतियों "
                    f"(जिनमें से **{high_count}** उच्च गंभीरता की हैं) की पहचान की गई।\n"
                    f"मैट्रिक्स के अनुसार विवरण: {counts_breakdown}।\n\n"
                    f"शीर्ष 3 विसंगति घटनाएं (ज्ञात प्रचार आयोजनों को लेबल किया गया है; अन्य सांख्यिकीय आउटलायर हैं):{events_bullet}"
                )
            elif language == "hinglish":
                return (
                    f"Full multi-metric daily anomaly detection scan (revenue, order count, AOV, delivery SLA, review CSAT) ke scope mein "
                    f"total **{total}** statistical anomalies detect hui hain (**{high_count}** high severity).\n"
                    f"Per-metric breakdown: {counts_breakdown}.\n\n"
                    f"Top 3 detected events (known events are catalog-labelled; others are neutral statistical outliers):{events_bullet}"
                )
            else:
                return (
                    f"Scope: Comprehensive multi-metric daily anomaly scan across core business series (revenue, orders, AOV, delivery SLA, CSAT). "
                    f"Detected **{total}** statistical anomalies (**{high_count}** high severity).\n"
                    f"Metric breakdown: {counts_breakdown}.\n\n"
                    f"Top 3 detected events (known events are labelled from the event catalog; other variations are neutral statistical outliers):{events_bullet}"
                )

        if language == "hi":
            return f"'{intent}' के लिए विश्लेषणात्मक क्वेरी PostgreSQL के विरुद्ध सफलतापूर्वक निष्पादित हुई।"
        elif language == "hinglish":
            return f"'{intent}' ke liye analytics query PostgreSQL se successfully run hui."
        return f"Analytics query for intent '{intent}' executed successfully against PostgreSQL. Evidence data loaded."

    @classmethod
    def synthesize_explanation_gemini(cls, client: Any, question: str, evidence: Dict[str, Any], language: Optional[str] = None, raise_on_error: bool = False) -> str:
        """
        Synthesizes grounded explanation using Gemini API based strictly on provided evidence.
        Respects question language (Hindi, Hinglish, English) while strictly maintaining Western digits 0-9.
        """
        if language is None:
            language = detect_language(question)

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

MULTILINGUAL RESPONSE INSTRUCTIONS:
- Detected question language: {language} ('hi' = Hindi, 'hinglish' = Hinglish, 'en' = English).
- Answer in the EXACT SAME LANGUAGE as the user question:
  * If Hindi ('hi'), answer in natural, grammatically correct Hindi using Devanagari script.
  * If Hinglish ('hinglish'), answer in natural conversational Hinglish using Roman script (e.g. 'PostgreSQL analytics ke anusaar, sabse zyada bikri...').
  * If English ('en'), answer in professional business English.
- CRITICAL DIGIT FORMAT RULE: Regardless of the language chosen (Hindi, Hinglish, or English), you MUST write all numbers, values, counts, percentages, and monetary amounts using standard Western digits 0-9 (e.g., 'R$ 13,221,498.11', '96,478', '4.16', '15.2%'). NEVER use Devanagari numerals (०-९) and NEVER spell out numbers as words. Always keep currency prefixed with 'R$'.

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
            if raise_on_error:
                raise
            logger.error(f"Gemini synthesis failed: {e}. Falling back to heuristic synthesis.")

        return cls.synthesize_explanation_heuristic(question, evidence, language=language)

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
        language = detect_language(question)

        # 1. Classification
        if client:
            classification = cls.classify_intent_gemini(client, question)
        else:
            classification = cls.classify_intent_heuristic(question)

        intent = classification["intent"]
        confidence = classification["confidence"]
        reason = classification["reason"]
        if classification.get("language"):
            language = classification["language"]

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
            fallback_msg = (
                "मुझे खेद है, मैं आपके प्रश्न को हमारे उपलब्ध व्यावसायिक विश्लेषण से मैप नहीं कर सका। कृपया अपना प्रश्न दोबारा पूछें।"
                if language == "hi" else
                ("Maaf kijiye, hum aapke question ko supported business analytics se map nahi kar paye. Please apna question rephrase karein."
                 if language == "hinglish" else
                 "I'm sorry, I couldn't confidently map your question to our available business analytics. "
                 "Please rephrase your question to focus on one of our supported topics: "
                 "product category revenue, monthly revenue trends, customer state sales, top sellers, "
                 "delivery performance, payment breakdown, executive KPIs, or data quality audits.")
            )
            return AskAIResponse(
                question=question,
                intent=intent if intent in SUPPORTED_INTENTS else "unknown",
                confidence=confidence,
                reason=reason,
                answer=fallback_msg,
                evidence=None,
                language=language,
                rephrase_suggested=True,
                grounding_verified=True
            )

        # 3. Route to existing validated analytics function
        try:
            evidence_dict = AIAnalyticsRouter.route_intent(intent)
        except (DatabaseUnavailableError, QueryTimeoutError) as e:
            latency_ms = (time.time() - start_time) * 1000.0
            logger.error(f"Database error while routing intent '{intent}': {e}", exc_info=True)
            AIAuditService.log(
                question=question,
                intent=intent,
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
            raise
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            logger.error(f"Error routing intent '{intent}': {e}", exc_info=True)
            AIAuditService.log(
                question=question,
                intent=intent,
                generated_sql=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e)
            )
            if not is_fixture_mode_allowed():
                assert_database_available(e, f"ai_routing_{intent}")
            return AskAIResponse(
                question=question,
                intent=intent,
                confidence=confidence,
                reason=f"Analytics routing failed: {str(e)}",
                answer="An error occurred while retrieving data from PostgreSQL analytics. Please try again later.",
                evidence=None,
                language=language,
                rephrase_suggested=False,
                grounding_verified=True
            )

        # 4. Synthesize explanation & verify numeric grounding
        grounding_verified = True
        if client:
            llm_answer = cls.synthesize_explanation_gemini(client, question, evidence_dict, language=language)
            # Run numeric faithfulness verifier
            if verify_numeric_grounding(llm_answer, evidence_dict["data"]):
                answer = llm_answer
                grounding_verified = True
            else:
                logger.warning(
                    f"LLM answer failed numeric verification. Falling back to heuristic synthesis for question: '{question}'"
                )
                answer = cls.synthesize_explanation_heuristic(question, evidence_dict, language=language)
                grounding_verified = False
        else:
            answer = cls.synthesize_explanation_heuristic(question, evidence_dict, language=language)
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
            language=language,
            rephrase_suggested=False,
            grounding_verified=grounding_verified
        )
