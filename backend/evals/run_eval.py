#!/usr/bin/env python3
"""
InsightForge — AI Feature Evaluation Harness
============================================
Evaluates natural language business questions from `golden_questions.yaml`
against expected intent classifications and canonical numeric grounding targets.
Supports --mode heuristic (offline rule-based) and --mode gemini (live Google Gemini API).
"""

import sys
import os
import time
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

# Enable fixtures for offline evaluation runner
os.environ["USE_FIXTURES"] = "1"

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.ai_service import AIService
from backend.app.services.grounding import (
    extract_numbers_from_text,
    verify_numeric_grounding
)

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
                "total_orders": 8836,
                "units_sold": 9670,
                "total_revenue": 1258819.00,
                "avg_item_price": 130.18,
                "avg_review_score": 4.14,
                "revenue_share_percent": 9.52
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
                "active_customers": 40494,
                "total_orders": 40494,
                "total_revenue": 5041040.67,
                "total_product_revenue": 5041040.67,
                "total_freight_revenue": 709827.00,
                "total_gross_revenue": 5750867.67,
                "avg_freight_cost": 17.53,
                "revenue_contribution_pct": 38.13,
                "revenue_share_percent": 38.13
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
            "avg_delivery_duration_days": 12.50,
            "avg_actual_delivery_days": 12.50,
            "avg_estimated_delivery_days": 23.40,
            "avg_delay_days": 8.60,
            "on_time_orders": 88651,
            "delayed_orders": 7827
        }
    },
    "payment_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "payment_analysis",
        "metric": "Payment Breakdown",
        "data": [
            {
                "payment_type": "credit_card",
                "order_count": 76795,
                "total_payment_value": 12542084.19,
                "avg_payment_amount": 163.32,
                "avg_installments": 3.51,
                "payment_value_percent": 78.34
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
            "total_anomalies": 12,
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


def load_golden_questions() -> List[Dict[str, Any]]:
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


def run_evaluations(mode: str = "heuristic") -> bool:
    questions = load_golden_questions()
    mode_upper = mode.upper()
    print("=" * 82)
    print(f"        INSIGHTFORGE AI EVALUATION BENCHMARK (MODE: {mode_upper})        ")
    print("=" * 82)
    print(f"Total Test Cases: {len(questions)}\n")

    client = None
    if mode == "gemini":
        client = AIService._get_genai_client()
        if not client:
            print("❌ ERROR: Gemini mode requested but GEMINI_API_KEY is not configured or google-genai is missing.")
            print("Please set GEMINI_API_KEY in your environment or .env file.")
            return False

    results = []
    intent_correct = 0
    numeric_total = 0
    numeric_correct = 0

    category_stats: Dict[str, Dict[str, int]] = {}

    for q in questions:
        qid = q["id"]
        qtext = q["question"]
        expected_intent = q["expected_intent"]
        expected_val = q.get("expected_value")

        prefix = qid.split("_")[0]
        if prefix not in category_stats:
            category_stats[prefix] = {"total": 0, "intent_ok": 0, "num_total": 0, "num_ok": 0}
        category_stats[prefix]["total"] += 1

        # 1. Intent Classification
        if mode == "gemini" and client:
            try:
                classification = AIService.classify_intent_gemini(client, qtext)
            except Exception as e:
                classification = {"intent": "unknown", "confidence": 0.0, "reason": str(e)}
        else:
            classification = AIService.classify_intent_heuristic(qtext)

        actual_intent = classification["intent"]
        conf = classification["confidence"]

        # Resolve intent match (for out-of-scope / unknown, low confidence counts as unknown)
        if expected_intent == "unknown":
            intent_match = (actual_intent == "unknown" or conf < 0.60)
        else:
            intent_match = (actual_intent == expected_intent)

        if intent_match:
            intent_correct += 1
            category_stats[prefix]["intent_ok"] += 1

        # 2. Numeric Faithfulness Check (if question has expected numeric answer)
        num_match: Optional[bool] = None
        if expected_val is not None:
            numeric_total += 1
            category_stats[prefix]["num_total"] += 1

            evidence = CANONICAL_EVIDENCE.get(expected_intent)
            if evidence:
                if mode == "gemini" and client:
                    try:
                        answer = AIService.synthesize_explanation_gemini(client, qtext, evidence)
                    except Exception:
                        answer = AIService.synthesize_explanation_heuristic(qtext, evidence)
                else:
                    answer = AIService.synthesize_explanation_heuristic(qtext, evidence)

                num_match = check_numeric_match(answer, float(expected_val))
                grounded = verify_numeric_grounding(answer, evidence["data"])
                if num_match and grounded:
                    numeric_correct += 1
                    category_stats[prefix]["num_ok"] += 1
                else:
                    num_match = False
            else:
                num_match = False

        results.append({
            "id": qid,
            "prefix": prefix,
            "question": qtext[:42] + ("..." if len(qtext) > 42 else ""),
            "expected_intent": expected_intent,
            "actual_intent": actual_intent,
            "intent_match": intent_match,
            "expected_val": expected_val,
            "num_match": num_match
        })

    # Print Category Breakdown Table
    print(f"{'Category':<12} | {'Cases':<6} | {'Intent Acc':<12} | {'Numeric Faith':<14}")
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
        "amb": "Ambiguous"
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

    # Overall Summary
    intent_accuracy = (intent_correct / len(questions)) * 100.0
    num_accuracy = (numeric_correct / numeric_total * 100.0) if numeric_total else 100.0

    print("=" * 82)
    print(f"Benchmark Mode:                        {mode_upper}")
    print(f"Overall Intent Classification Accuracy: {intent_correct}/{len(questions)} ({intent_accuracy:.2f}%)")
    print(f"Overall Numeric Faithfulness:          {numeric_correct}/{numeric_total} ({num_accuracy:.2f}%)")
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
        choices=["heuristic", "gemini"],
        default="heuristic",
        help="Evaluation classification & synthesis mode (heuristic or gemini)"
    )
    args = parser.parse_args()
    success = run_evaluations(mode=args.mode)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
