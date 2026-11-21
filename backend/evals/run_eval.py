#!/usr/bin/env python3
"""
InsightForge — AI Feature Evaluation Harness
============================================
Evaluates natural language business questions from `golden_questions.yaml`
against expected intent classifications and canonical numeric grounding targets.
Fully operational offline using heuristic classification & canonical evidence mocks.
"""

import sys
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

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
                "product_category_name_english": "health_beauty",
                "total_revenue": 1258819.00,
                "revenue_contribution_pct": 9.52,
                "units_sold": 9670,
                "avg_review_score": 4.14
            },
            {
                "product_category_name_english": "watches_gifts",
                "total_revenue": 1205005.68,
                "revenue_contribution_pct": 9.11,
                "units_sold": 5624,
                "avg_review_score": 4.02
            },
            {
                "product_category_name_english": "bed_bath_table",
                "total_revenue": 1036988.68,
                "revenue_contribution_pct": 7.84,
                "units_sold": 11115,
                "avg_review_score": 3.88
            }
        ]
    },
    "state_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "state_analysis",
        "metric": "Customer State Sales Analytics",
        "data": [
            {
                "customer_state": "SP",
                "total_revenue": 5041040.67,
                "revenue_contribution_pct": 38.13,
                "delivered_orders": 40494
            },
            {
                "customer_state": "RJ",
                "total_revenue": 1709477.34,
                "revenue_contribution_pct": 12.93,
                "delivered_orders": 12350
            },
            {
                "customer_state": "MG",
                "total_revenue": 1515286.72,
                "revenue_contribution_pct": 11.46,
                "delivered_orders": 11354
            }
        ]
    },
    "seller_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "seller_analysis",
        "metric": "Seller Performance Analytics",
        "data": [
            {
                "seller_id": "4869f7a5dfa277a7dca6462dcf3b52b2",
                "total_revenue": 229472.63,
                "units_sold": 1156,
                "avg_review_score": 4.12
            },
            {
                "seller_id": "53243585a1d6dc2643021fd1853d8905",
                "total_revenue": 222776.05,
                "units_sold": 410,
                "avg_review_score": 4.14
            }
        ]
    },
    "delivery_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "delivery_analysis",
        "metric": "Delivery SLA Performance",
        "data": {
            "on_time_delivery_pct": 91.90,
            "delay_percentage": 8.10,
            "avg_delivery_duration_days": 12.50,
            "avg_delay_days": 11.20,
            "delayed_order_count": 7827,
            "on_time_order_count": 88651
        }
    },
    "payment_analysis": {
        "source": "PostgreSQL analytics",
        "intent": "payment_analysis",
        "metric": "Payment Method Analytics",
        "data": [
            {
                "payment_type": "credit_card",
                "total_payment_value": 12542084.19,
                "payment_value_pct": 78.34,
                "order_count": 74304
            },
            {
                "payment_type": "boleto",
                "total_payment_value": 2869361.27,
                "payment_value_pct": 17.92,
                "order_count": 19191
            }
        ]
    },
    "revenue_trend": {
        "source": "PostgreSQL analytics",
        "intent": "revenue_trend",
        "metric": "Monthly Sales Trend",
        "data": [
            {
                "year_month": "2017-11",
                "gross_revenue": 1197480.00,
                "mom_revenue_growth_pct": 53.20,
                "delivered_order_count": 7289
            },
            {
                "year_month": "2018-04",
                "gross_revenue": 1160785.48,
                "mom_revenue_growth_pct": 1.20,
                "delivered_order_count": 6798
            }
        ]
    },
    "data_quality": {
        "source": "PostgreSQL audit engine",
        "intent": "data_quality",
        "metric": "Data Integrity Audit Report",
        "data": {
            "audit_status": "Healthy",
            "primary_key_uniqueness": "PASS (0 duplicate PKs across 7 tables)",
            "foreign_key_integrity": "PASS (0 orphan records detected)",
            "domain_bounds_status": "PASS (0 negative prices or invalid scores)",
            "timestamp_consistency": "PASS (0 timestamp anomalies)"
        }
    }
}


def load_golden_questions() -> List[Dict[str, Any]]:
    yaml_path = Path(__file__).resolve().parent / "golden_questions.yaml"
    if not yaml_path.exists():
        print(f"Error: {yaml_path} does not exist!")
        sys.exit(1)
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("questions", [])


def check_numeric_match(answer_text: str, expected_val: float, tolerance_pct: float = 2.0) -> bool:
    """Check if expected_val appears in answer_text within tolerance."""
    extracted = extract_numbers_from_text(answer_text)
    for n in extracted:
        if abs(n - expected_val) <= 0.05:
            return True
        if abs(expected_val) > 0.01:
            rel_err = abs(n - expected_val) / abs(expected_val) * 100.0
            if rel_err <= tolerance_pct:
                return True
        # Check percent scaling (e.g. 91.9 vs 0.919)
        if abs(n - (expected_val * 100.0)) <= 0.05 or abs((n / 100.0) - expected_val) <= 0.005:
            return True
    return False


def run_evaluations() -> bool:
    questions = load_golden_questions()
    print("=" * 82)
    print("        INSIGHTFORGE AI EVALUATION BENCHMARK (OFFLINE HEURISTIC)        ")
    print("=" * 82)
    print(f"Total Test Cases: {len(questions)}\n")

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

        # 1. Heuristic Classification
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

            # Get evidence mock for this intent
            evidence = CANONICAL_EVIDENCE.get(expected_intent)
            if evidence:
                answer = AIService.synthesize_explanation_heuristic(qtext, evidence)
                num_match = check_numeric_match(answer, float(expected_val))
                # Also verify that the answer numbers are properly grounded
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
    print(f"Overall Intent Classification Accuracy: {intent_correct}/{len(questions)} ({intent_accuracy:.2f}%)")
    print(f"Overall Numeric Faithfulness:          {numeric_correct}/{numeric_total} ({num_accuracy:.2f}%)")
    print("=" * 82)

    passed = intent_accuracy >= 80.0 and num_accuracy >= 80.0
    if passed:
        print(" Evaluation Benchmark PASSED (All criteria >= 80.0%)")
    else:
        print("❌ Evaluation Benchmark FAILED (Criteria below threshold)")
    return passed


if __name__ == "__main__":
    success = run_evaluations()
    sys.exit(0 if success else 1)
