#!/usr/bin/env python3
"""
InsightForge — AI Feature Evaluation Harness
============================================
Evaluates natural language business questions from `golden_questions.yaml`
against expected intent classifications and canonical numeric grounding targets.
Supports --mode heuristic (offline rule-based) and --mode gemini (live Google Gemini API).

Environment variables:
  GEMINI_API_KEY        Default Gemini key (also used for evals if GEMINI_API_KEY_EVAL is unset)
  GEMINI_API_KEY_EVAL   Optional separate Gemini key for eval runs (avoids sharing quota)
"""

import sys
import os
import re
import json
import time
import hashlib
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml

# Enable fixtures for offline evaluation runner
os.environ["USE_FIXTURES"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings
from backend.app.services.ai_service import AIService, detect_language
from backend.app.services.ai_analytics_router import AIAnalyticsRouter
from backend.app.services.grounding import (
    extract_numbers_from_text,
    verify_numeric_grounding
)

# On-disk Gemini response cache directory & file
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_FILE = CACHE_DIR / "gemini_eval_cache.json"


class GeminiEvalCache:
    """Thread-safe persistent cache for Gemini evaluation calls keyed by model + prompt."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        if self.enabled:
            self._load()

    def _load(self):
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {}

    def get(self, model: str, prompt: str) -> Optional[Any]:
        if not self.enabled:
            return None
        key = hashlib.sha256(f"{model}:{prompt}".encode("utf-8")).hexdigest()
        with self._lock:
            entry = self._data.get(key)
            if entry and isinstance(entry, dict):
                return entry.get("response")
        return None

    def set(self, model: str, prompt: str, prompt_type: str, response: Any):
        if not self.enabled:
            return
        key = hashlib.sha256(f"{model}:{prompt}".encode("utf-8")).hexdigest()
        with self._lock:
            self._data[key] = {
                "model": model,
                "prompt_type": prompt_type,
                "prompt": prompt[:300],
                "response": response,
                "cached_at": time.time()
            }
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2)
            except Exception:
                pass


def call_gemini_with_backoff(func, *args, max_retries: int = 4, base_delay: float = 2.0, **kwargs):
    """Executes a Gemini API call with exponential backoff on 429/ResourceExhausted errors."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e)
            if ("RESOURCE_EXHAUSTED" in err_str or "429" in err_str) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            raise

# Canonical offline evidence mocks for deterministic, database-independent evaluations
CANONICAL_EVIDENCE: Dict[str, Dict[str, Any]] = {
    "kpi_summary": {
        "source": "PostgreSQL analytics",
        "intent": "kpi_summary",
        "metric": "Executive KPI Summary",
        "data": {
            "total_product_revenue": 13221498.11,
            "total_freight_revenue": 2198275.64,
            "total_gross_revenue": 15419773.75,
            "total_delivered_orders": 96478,
            "total_units_sold": 110197,
            "aov": 159.83,
            "avg_review_score": 4.16,
            "csat": 4.16
        }
    },
    "category_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "category_analysis",
        "metric": "Product Category Analytics",
        "data": [
            {
                "category": "health_beauty",
                "total_orders": 8647,
                "units_sold": 9465,
                "total_revenue": 1233131.72,
                "avg_item_price": 130.28,
                "avg_review_score": 4.19,
                "revenue_share_percent": 9.33
            },
            {
                "category": "watches_gifts",
                "total_orders": 4991,
                "units_sold": 5624,
                "total_revenue": 1205005.68,
                "avg_item_price": 214.26,
                "avg_review_score": 4.02,
                "revenue_share_percent": 9.11
            },
            {
                "category": "bed_bath_table",
                "total_orders": 9417,
                "units_sold": 11115,
                "total_revenue": 1036988.68,
                "avg_item_price": 93.30,
                "avg_review_score": 3.88,
                "revenue_share_percent": 7.84
            }
        ]
    },
    "state_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "state_analysis",
        "metric": "Customer State Sales Performance",
        "data": [
            {
                "state": "SP",
                "customer_state": "SP",
                "active_customers": 39156,
                "total_orders": 40501,
                "total_revenue": 5769703.15,
                "total_product_revenue": 5067633.16,
                "total_freight_revenue": 702069.99,
                "total_gross_revenue": 5769703.15,
                "avg_freight_cost": 15.12,
                "revenue_contribution_pct": 38.33,
                "revenue_share_percent": 38.33
            },
            {
                "state": "RJ",
                "customer_state": "RJ",
                "active_customers": 12350,
                "total_orders": 12350,
                "total_product_revenue": 1709477.34,
                "total_freight_revenue": 298124.00,
                "total_gross_revenue": 2007601.34,
                "avg_freight_cost": 24.14,
                "revenue_share_percent": 12.93
            }
        ]
    },
    "seller_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "seller_analysis",
        "metric": "Seller Fulfillment Performance",
        "data": [
            {
                "seller_id": "4869f7a5dfa277a7dca6462dcf3b52b2",
                "seller_city": "guariba",
                "seller_state": "SP",
                "total_orders_fulfilled": 1132,
                "units_sold": 1156,
                "unique_products_offered": 82,
                "total_sales_revenue": 229472.63,
                "avg_seller_review_score": 4.12
            }
        ]
    },
    "delivery_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "delivery_analysis",
        "metric": "Delivery SLA Performance",
        "data": {
            "on_time_delivery_pct": 91.90,
            "on_time_percentage": 91.90,
            "delay_percentage": 8.10,
            "avg_delivery_duration_days": 10.88,
            "avg_actual_delivery_days": 10.88,
            "avg_estimated_delivery_days": 23.40,
            "avg_delay_days": 8.60,
            "on_time_orders": 88644,
            "delayed_orders": 7826
        }
    },
    "payment_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "payment_analysis",
        "metric": "Payment Breakdown",
        "data": [
            {
                "payment_type": "credit_card",
                "order_count": 74304,
                "total_payment_value": 12101094.88,
                "avg_payment_amount": 162.24,
                "avg_installments": 3.50,
                "payment_value_percent": 78.48
            },
            {
                "payment_type": "boleto",
                "order_count": 19784,
                "total_payment_value": 2869361.27,
                "avg_payment_amount": 145.03,
                "avg_installments": 1.00,
                "payment_value_percent": 17.92
            }
        ]
    },
    "revenue_trend": {
        "source": "PostgreSQL analytics",
        "intent": "revenue_trend",
        "metric": "Monthly Revenue Trend",
        "data": [
            {
                "month": "2017-11",
                "total_orders": 7289,
                "total_items_sold": 8560,
                "gross_revenue": 1197480.00,
                "aov": 164.29,
                "mom_revenue_growth_pct": 80.31
            },
            {
                "month": "2018-04",
                "total_orders": 6798,
                "total_items_sold": 7920,
                "gross_revenue": 1160785.48,
                "aov": 170.75,
                "mom_revenue_growth_pct": 18.06
            }
        ]
    },
    "data_quality": {
        "source": "PostgreSQL analytics",
        "intent": "data_quality",
        "metric": "Data Quality Audit Report",
        "data": {
            "audit_status": "PASS",
            "table_row_counts": {"orders": 99441, "order_items": 112650},
            "primary_key_uniqueness": "PASS (0 duplicates)",
            "foreign_key_integrity": "PASS (0 orphans)",
            "domain_bounds_status": "PASS",
            "join_safety_status": "PASS (0.00 discrepancy)"
        }
    },
    "anomaly_detection": {
        "source": "PostgreSQL analytics",
        "intent": "anomaly_detection",
        "metric": "Statistical Anomaly Detection",
        "data": {
            "total_anomalies": 111,
            "top_anomalies": [
                {
                    "metric": "gross_revenue",
                    "dimension": "overall",
                    "period": "2017-11-24",
                    "observed": 176940.50,
                    "expected": 28450.00,
                    "deviation_score": 6.85,
                    "severity": "high",
                    "direction": "spike",
                    "method": "rolling_zscore",
                    "known_event_candidate": "Black Friday 2017 (promotional_peak)"
                }
            ]
        }
    }
}


def load_golden_questions(questions_path: Optional[str] = None) -> List[Dict[str, Any]]:
    if questions_path:
        yaml_path = Path(questions_path)
        if not yaml_path.is_absolute():
            yaml_path = (Path(__file__).resolve().parent / questions_path).resolve()
    else:
        yaml_path = Path(__file__).resolve().parent / "golden_questions.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("questions", data.get("golden_questions", []))


def check_numeric_match(answer_text: str, expected_val: float, tolerance_pct: float = 2.0) -> bool:
    extracted = extract_numbers_from_text(answer_text)
    if not extracted:
        return False
    for n in extracted:
        if abs(n - expected_val) <= 0.05:
            return True
        if expected_val != 0:
            rel_err = abs(n - expected_val) / abs(expected_val) * 100.0
            if rel_err <= tolerance_pct:
                return True
        if abs(n - (expected_val * 100.0)) <= 0.05 or abs((n / 100.0) - expected_val) <= 0.005:
            return True
    return False


def run_sql_evaluations(questions_path: Optional[str] = None, limit: Optional[int] = None) -> bool:
    """
    Evaluates dynamic Text-to-SQL queries against live PostgreSQL.
    Strictly requires live PostgreSQL and GEMINI_API_KEY (no fixtures or fake data).
    """
    from sqlalchemy import text
    from backend.app.config import settings
    from backend.app.database import readonly_engine
    from backend.app.services.sql_validator import SQLValidator
    from backend.app.services.text_to_sql_service import TextToSQLService

    print("=" * 86)
    print("      INSIGHTFORGE DYNAMIC TEXT-TO-SQL LIVE BENCHMARK (REAL POSTGRESQL)")
    print("=" * 86)

    # 1. Check GEMINI_API_KEY
    api_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        print("\n❌ Error: GEMINI_API_KEY is not configured.")
        print("Live dynamic-SQL evaluation requires a valid Gemini API key in your environment or .env.")
        print("Exiting without faking evaluation numbers.\n")
        sys.exit(1)

    # 2. Check live PostgreSQL database connection
    try:
        with readonly_engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except Exception as e:
        print("\n❌ Error: PostgreSQL database is not reachable.")
        print(f"Details: {e}")
        print("Live dynamic-SQL evaluation requires an active, reachable PostgreSQL database.")
        print("Exiting without faking evaluation numbers.\n")
        sys.exit(1)

    all_questions = load_golden_questions(questions_path=questions_path)
    sql_questions = [q for q in all_questions if q.get("id", "").startswith("sql_") or q.get("expected_intent") == "text_to_sql"]

    if limit is not None and limit > 0:
        sql_questions = sql_questions[:limit]

    if not sql_questions:
        print(f"No SQL benchmark questions found in {questions_path or 'golden_questions.yaml'}.")
        return False

    client = AIService._get_genai_client()
    print(f"Loaded {len(sql_questions)} dynamic-SQL test cases.\n")

    valid_count = 0
    exec_count = 0
    accuracy_count = 0
    all_case_details = []

    print(f"{'ID':<7} | {'SQL Valid':<10} | {'Exec OK':<10} | {'Expected':<12} | {'Actual':<12} | {'Result'}")
    print("-" * 75)

    for q in sql_questions:
        qid = q["id"]
        qtext = q["question"]
        ref_sql = q.get("reference_sql")

        # 1. Generate SQL via TextToSQLService with self-correction retry loop
        gen_res = TextToSQLService.generate_and_validate_sql(client, qtext, max_retries=2)
        gen_sql = gen_res.get("sql", "") or ""
        executed = gen_res.get("success", False)
        exec_result = f"OK ({gen_res.get('row_count', 0)} rows)" if executed else f"Exec Error: {str(gen_res.get('error'))[:35]}"
        actual_val = None
        expected_val = None
        match = False

        # 2. AST Validation Verdict (Computed from validator verdict ONLY)
        if gen_sql:
            is_valid, sanitized_sql, val_err = SQLValidator.validate(gen_sql)
            if is_valid:
                valid_count += 1
                sql_valid = True
                rejection_reason = "None"
            else:
                sql_valid = False
                rejection_reason = str(val_err)
        else:
            sql_valid = False
            rejection_reason = "No SQL produced"

        # 3. Ground Truth from Reference SQL & Output Column Identification
        ref_col_name = None
        if ref_sql:
            try:
                with readonly_engine.connect() as conn:
                    result_proxy = conn.execute(text(ref_sql))
                    ref_keys = list(result_proxy.keys()) if hasattr(result_proxy, "keys") else []
                    ref_col_name = ref_keys[0].lower() if ref_keys else None
                    ref_res = result_proxy.fetchone()
                    if ref_res and len(ref_res) > 0 and ref_res[0] is not None:
                        try:
                            expected_val = float(ref_res[0])
                        except (ValueError, TypeError):
                            expected_val = None
            except Exception:
                pass

        target_col = q.get("expected_column") or ref_col_name

        # 4. Target Column Numeric Result Extraction from Executed Rows
        if executed:
            exec_count += 1
            rows = gen_res.get("rows", [])
            if rows:
                first_row = rows[0]  # Dictionary of column_name -> value, or scalar
                matched_val = None

                # (a) Handle scalar primitive directly
                if isinstance(first_row, (int, float)):
                    matched_val = float(first_row)
                elif isinstance(first_row, dict):
                    # (b) Explicit target column match
                    if target_col:
                        t_lower = target_col.lower()
                        for k, v in first_row.items():
                            if k.lower() == t_lower and v is not None:
                                try:
                                    matched_val = float(v)
                                    break
                                except (ValueError, TypeError):
                                    pass

                        # Synonyms / alias matching
                        if matched_val is None:
                            for k, v in first_row.items():
                                if (t_lower in k.lower() or k.lower() in t_lower) and v is not None:
                                    try:
                                        matched_val = float(v)
                                        break
                                    except (ValueError, TypeError):
                                        pass

                    # (c) Exactly one numeric column exists in the row
                    if matched_val is None:
                        numeric_cols = []
                        for k, v in first_row.items():
                            if v is not None:
                                try:
                                    numeric_cols.append(float(v))
                                except (ValueError, TypeError):
                                    continue
                        if len(numeric_cols) == 1:
                            matched_val = numeric_cols[0]

                    # (d) Fallback to first column value (ensures wrong column fails)
                    if matched_val is None:
                        for k, v in first_row.items():
                            if v is not None:
                                try:
                                    matched_val = float(v)
                                    break
                                except (ValueError, TypeError):
                                    continue

                elif isinstance(first_row, (list, tuple)) and len(first_row) > 0:
                    try:
                        matched_val = float(first_row[0])
                    except (ValueError, TypeError):
                        pass

                actual_val = matched_val

        # 5. Strict comparison: ONLY compare the selected actual_val with expected_val
        if expected_val is not None and actual_val is not None:
            if abs(actual_val - expected_val) <= 0.05 or (expected_val != 0 and abs(actual_val - expected_val) / abs(expected_val) <= 0.02):
                match = True
                accuracy_count += 1

        case_detail = {
            "id": qid,
            "question": qtext,
            "generated_sql": gen_sql,
            "validator_verdict": "VALID" if sql_valid else "DENIED",
            "rejection_reason": rejection_reason,
            "execution_status": exec_result,
            "returned_val": actual_val,
            "reference_val": expected_val,
            "match": match
        }
        all_case_details.append(case_detail)

        exp_str = f"{expected_val:,.2f}" if expected_val is not None else "N/A"
        act_str = f"{actual_val:,.2f}" if actual_val is not None else "N/A"
        verdict_str = "PASS" if match else ("OK" if executed else "FAIL")
        print(f"[{qid}] Q: {qtext}\n  SQL: {gen_sql}\n  Verdict: {case_detail['validator_verdict']} (Reason: {rejection_reason}) | Exec: {exec_result} | Exp: {exp_str} | Act: {act_str} | Result: {verdict_str}\n", flush=True)
        time.sleep(4.0)

    n_total = len(sql_questions)
    validity_rate = (valid_count / n_total) * 100.0
    exec_rate = (exec_count / n_total) * 100.0
    acc_rate = (accuracy_count / n_total) * 100.0

    print("=" * 86)
    print(f"Total Dynamic SQL Cases:        {n_total}")
    print(f"SQL AST Validity Rate:          {valid_count}/{n_total} ({validity_rate:.1f}%)")
    print(f"Execution Success Rate:         {exec_count}/{n_total} ({exec_rate:.1f}%)")
    print(f"Result Accuracy (Ground Truth):  {accuracy_count}/{n_total} ({acc_rate:.1f}%)")
    print("=" * 86)

    return validity_rate >= 80.0


def run_evaluations(
    mode: str = "heuristic",
    live: bool = False,
    questions_path: Optional[str] = None,
    limit: Optional[int] = None,
    no_cache: bool = False
) -> bool:
    if live and "USE_FIXTURES" in os.environ:
        del os.environ["USE_FIXTURES"]
    all_questions = load_golden_questions(questions_path=questions_path)
    questions = [q for q in all_questions if not q.get("id", "").startswith("sql_")]
    if limit is not None and limit > 0:
        questions = questions[:limit]

    mode_upper = mode.upper()
    evidence_source = "LIVE DATABASE (PostgreSQL schema insightforge)" if live else "CANONICAL FIXTURES (Offline Benchmark)"
    print("=" * 82)
    print(f"        INSIGHTFORGE AI EVALUATION BENCHMARK (MODE: {mode_upper})        ")
    print(f"        Evidence Source: {evidence_source}")
    print("=" * 82)
    print(f"Total Test Cases: {len(questions)}\n")

    live_anomaly_count = None
    if live:
        try:
            from backend.app.services.anomaly_service import AnomalyService
            live_scan = AnomalyService.run_full_scan(grain="daily")
            live_anomaly_count = live_scan.anomalies_detected
        except Exception:
            live_anomaly_count = None

    client = None
    eval_cache = GeminiEvalCache(enabled=(not no_cache))
    quota_state = {"exhausted": False}

    if mode == "gemini":
        eval_key = os.environ.get("GEMINI_API_KEY_EVAL") or os.environ.get("GEMINI_API_KEY", "")
        if eval_key:
            os.environ["GEMINI_API_KEY"] = eval_key
        client = AIService._get_genai_client()
        if not client:
            print("❌ ERROR: Gemini mode requested but GEMINI_API_KEY is not configured or google-genai is missing.")
            print("Please set GEMINI_API_KEY (or GEMINI_API_KEY_EVAL) in your environment or .env file.")
            return False

    def process_case(q: Dict[str, Any]) -> Dict[str, Any]:
        qid = q["id"]
        qtext = q["question"]
        expected_intent = q["expected_intent"]
        expected_val = q.get("expected_value")
        if qid == "anom_02" and live and live_anomaly_count is not None:
            expected_val = float(live_anomaly_count)
        qlang = q.get("language") or detect_language(qtext)
        prefix = qid.split("_")[0]

        intent_source = "heuristic"
        actual_intent = "unknown"
        conf = 0.0

        # 1. Intent Classification
        if mode == "gemini" and client:
            if quota_state["exhausted"]:
                actual_intent = "NOT_RUN_QUOTA"
                intent_source = "not_run_quota"
            else:
                cached_intent = eval_cache.get(settings.GEMINI_MODEL, f"classify:{qtext}")
                if cached_intent:
                    classification = cached_intent
                    actual_intent = classification["intent"]
                    conf = classification["confidence"]
                    intent_source = "cached"
                else:
                    try:
                        classification = call_gemini_with_backoff(AIService.classify_intent_gemini, client, qtext, raise_on_error=True)
                        eval_cache.set(settings.GEMINI_MODEL, f"classify:{qtext}", "classify", classification)
                        actual_intent = classification["intent"]
                        conf = classification["confidence"]
                        intent_source = "live"
                    except Exception as e:
                        err_str = str(e)
                        if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                            quota_state["exhausted"] = True
                            actual_intent = "NOT_RUN_QUOTA"
                            intent_source = "not_run_quota"
                        else:
                            classification = AIService.classify_intent_heuristic(qtext)
                            actual_intent = classification["intent"]
                            conf = classification["confidence"]
                            intent_source = "fallback_heuristic"
        else:
            classification = AIService.classify_intent_heuristic(qtext)
            actual_intent = classification["intent"]
            conf = classification["confidence"]
            intent_source = "heuristic"

        # Resolve intent match
        if actual_intent == "NOT_RUN_QUOTA":
            intent_match = None
        elif expected_intent == "unknown":
            intent_match = (actual_intent == "unknown" or conf < 0.60)
        else:
            intent_match = (actual_intent == expected_intent)

        # 2. Numeric Faithfulness
        numeric_source = None
        num_match = None
        quota_skipped_numeric = False

        if expected_val is not None:
            if live:
                try:
                    evidence = AIAnalyticsRouter.route_intent(expected_intent)
                except Exception:
                    evidence = None
            else:
                evidence = CANONICAL_EVIDENCE.get(expected_intent)

            if evidence:
                target_val = float(expected_val)
                ev_data = evidence.get("data", {})
                if live:
                    if expected_intent == "anomaly_detection" and isinstance(ev_data, dict):
                        if qid in ("anom_02", "anom_07") or "how many" in qtext.lower() or "detect any" in qtext.lower() or "total" in qtext.lower():
                            target_val = float(ev_data.get("total_anomalies", expected_val))
                    elif expected_intent == "delivery_analysis" and isinstance(ev_data, dict):
                        if qid in ("del_02", "ml_hi_07"):
                            target_val = float(ev_data.get("avg_actual_delivery_days", expected_val))

                if mode == "gemini" and client:
                    if quota_state["exhausted"]:
                        quota_skipped_numeric = True
                        numeric_source = "not_run_quota"
                    else:
                        synth_prompt = f"synthesize:{qtext}:{json.dumps(ev_data, sort_keys=True)}:{qlang}"
                        cached_answer = eval_cache.get(settings.GEMINI_MODEL, synth_prompt)
                        if cached_answer:
                            answer = cached_answer
                            numeric_source = "cached"
                        else:
                            try:
                                answer = call_gemini_with_backoff(AIService.synthesize_explanation_gemini, client, qtext, evidence, language=qlang, raise_on_error=True)
                                eval_cache.set(settings.GEMINI_MODEL, synth_prompt, "synthesize", answer)
                                numeric_source = "live"
                            except Exception as e:
                                err_str = str(e)
                                if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                                    quota_state["exhausted"] = True
                                    quota_skipped_numeric = True
                                    numeric_source = "not_run_quota"
                                else:
                                    answer = AIService.synthesize_explanation_heuristic(qtext, evidence, language=qlang)
                                    numeric_source = "fallback_heuristic"
                else:
                    answer = AIService.synthesize_explanation_heuristic(qtext, evidence, language=qlang)
                    numeric_source = "heuristic"

                if quota_skipped_numeric:
                    num_match = None
                else:
                    num_match = check_numeric_match(answer, target_val)
                    grounded = verify_numeric_grounding(answer, ev_data)
                    num_match = bool(num_match and grounded)
            else:
                num_match = False

        return {
            "id": qid,
            "prefix": prefix,
            "question": qtext[:42] + ("..." if len(qtext) > 42 else ""),
            "qlang": qlang,
            "expected_intent": expected_intent,
            "actual_intent": actual_intent,
            "intent_match": intent_match,
            "intent_source": intent_source,
            "expected_val": expected_val,
            "num_match": num_match,
            "numeric_source": numeric_source,
            "quota_skipped_numeric": quota_skipped_numeric,
        }

    # Execute cases (concurrently up to 4 workers if Gemini mode and multiple cases)
    results = []
    max_workers = 4 if mode == "gemini" and len(questions) > 1 else 1
    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(process_case, q): idx for idx, q in enumerate(questions)}
            indexed_results = []
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                res = future.result()
                indexed_results.append((idx, res))
            indexed_results.sort(key=lambda x: x[0])
            results = [r[1] for r in indexed_results]
    else:
        for q in questions:
            results.append(process_case(q))

    # Aggregate stats and print evaluation trace
    intent_correct = 0
    numeric_total = 0
    numeric_correct = 0

    category_stats: Dict[str, Dict[str, int]] = {}
    language_stats: Dict[str, Dict[str, int]] = {
        "en": {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0},
        "hi": {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0},
        "hinglish": {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0}
    }

    live_gemini_calls = 0
    cached_gemini_calls = 0
    not_run_quota_calls = 0

    for r in results:
        qid = r["id"]
        prefix = r["prefix"]
        qlang = r["qlang"]

        if qlang not in language_stats:
            language_stats[qlang] = {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0}
        if prefix not in category_stats:
            category_stats[prefix] = {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0}

        category_stats[prefix]["total"] += 1
        language_stats[qlang]["total"] += 1

        for src in (r["intent_source"], r["numeric_source"]):
            if src == "live":
                live_gemini_calls += 1
            elif src == "cached":
                cached_gemini_calls += 1
            elif src == "not_run_quota":
                not_run_quota_calls += 1

        if mode == "gemini":
            label = "[LIVE]" if r["intent_source"] == "live" else ("[CACHED]" if r["intent_source"] == "cached" else ("[NOT_RUN]" if r["intent_source"] == "not_run_quota" else "[HEURISTIC]"))
            print(f"  {label:<10} {qid}: intent={r['actual_intent']} (expected: {r['expected_intent']})")

        if r["intent_match"]:
            intent_correct += 1
            category_stats[prefix]["intent_ok"] += 1
            language_stats[qlang]["intent_ok"] += 1

        if r["expected_val"] is not None and not r["quota_skipped_numeric"]:
            numeric_total += 1
            category_stats[prefix]["num_total"] += 1
            language_stats[qlang]["num_total"] += 1
            if r["num_match"]:
                numeric_correct += 1
                category_stats[prefix]["num_ok"] += 1
                language_stats[qlang]["num_ok"] += 1

    # Print Category Breakdown Table
    print(f"\n{'Category':<12} | {'Cases':<6} | {'Intent Acc':<12} | {'Numeric Faith':<14}")
    print("-" * 52)
    cat_names = {
        "cat": "Category",
        "st": "State",
        "sel": "Seller",
        "del": "Delivery",
        "pay": "Payment",
        "trd": "Trend",
        "kpi": "KPIs",
        "dq": "Data Quality",
        "anom": "Anomalies",
        "oos": "Out-of-Scope",
        "amb": "Ambiguous",
        "ml": "Multilingual"
    }

    for prefix, stats in category_stats.items():
        name = cat_names.get(prefix, prefix)
        total = stats["total"]
        i_ok = stats["intent_ok"]
        i_pct = (i_ok / total * 100.0) if total else 0.0

        n_tot = stats["num_total"]
        n_ok = stats["num_ok"]
        n_str = f"{n_ok}/{n_tot} ({(n_ok/n_tot*100.0):.1f}%)" if n_tot > 0 else "N/A"

        print(f"{name:<12} | {total:<6} | {i_ok}/{total} ({i_pct:.1f}%) | {n_str:<14}")

    # Print Language Breakdown Table
    print("\n" + "=" * 52)
    print("LANGUAGE BREAKDOWN (Level 4 Multilingual Evaluation)")
    print("=" * 52)
    print(f"{'Language':<14} | {'Cases':<6} | {'Intent Acc':<12} | {'Numeric Faith':<14}")
    print("-" * 52)
    lang_labels = {
        "en": "English",
        "hi": "Hindi (Dev)",
        "hinglish": "Hinglish"
    }
    for lk, lstats in language_stats.items():
        lname = lang_labels.get(lk, lk)
        ltotal = lstats["total"]
        li_ok = lstats["intent_ok"]
        li_pct = (li_ok / ltotal * 100.0) if ltotal else 0.0

        ln_tot = lstats["num_total"]
        ln_ok = lstats["num_ok"]
        ln_str = f"{ln_ok}/{ln_tot} ({(ln_ok/ln_tot*100.0):.1f}%)" if ln_tot > 0 else "N/A"

        print(f"{lname:<14} | {ltotal:<6} | {li_ok}/{ltotal} ({li_pct:.1f}%) | {ln_str:<14}")

    # Overall Summary
    intent_accuracy = (intent_correct / len(questions)) * 100.0 if questions else 0.0
    num_accuracy = (numeric_correct / numeric_total * 100.0) if numeric_total else 100.0

    print("=" * 82)
    print(f"Benchmark Mode:                         {mode_upper}")
    if mode == "gemini":
        print(f"Gemini API Execution Breakdown:")
        print(f"  - Live Gemini API Calls:              {live_gemini_calls}")
        print(f"  - Cached Responses:                   {cached_gemini_calls}")
        print(f"  - Not Run / Quota Skipped:            {not_run_quota_calls}")
    print(f"Overall Intent Classification Accuracy:  {intent_correct}/{len(questions)} ({intent_accuracy:.2f}%)")
    print(f"Overall Numeric Faithfulness:           {numeric_correct}/{numeric_total} ({num_accuracy:.2f}%)")
    print("=" * 82)

    passed = intent_accuracy >= 80.0 and num_accuracy >= 80.0
    if passed:
        print(f" Evaluation Benchmark PASSED ({mode_upper}: All criteria >= 80.0%)")
    else:
        print(f"❌ Evaluation Benchmark FAILED ({mode_upper}: Criteria below threshold)")
    return passed


def main():
    parser = argparse.ArgumentParser(description="InsightForge AI Evaluation Harness")
    parser.add_argument(
        "--mode",
        choices=["heuristic", "gemini", "sql"],
        default="heuristic",
        help="Evaluation classification & synthesis mode (heuristic, gemini, or sql)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Compute numeric-faithfulness evidence from the live PostgreSQL database instead of canonical fixtures"
    )
    parser.add_argument(
        "--questions",
        default=None,
        help="Custom YAML questions dataset (e.g. golden_questions_holdout.yaml)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only first N evaluation cases"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Bypass on-disk Gemini response cache"
    )
    args = parser.parse_args()
    if args.mode == "sql":
        success = run_sql_evaluations(questions_path=args.questions, limit=args.limit)
    else:
        success = run_evaluations(
            mode=args.mode,
            live=args.live,
            questions_path=args.questions,
            limit=args.limit,
            no_cache=args.no_cache
        )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
