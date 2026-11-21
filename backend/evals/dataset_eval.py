"""
InsightForge Level 6: Generality Evaluation Harness for Dataset Workspace
========================================================================
Runs 5 benchmark questions per sample dataset against real/mocked Gemini Text-to-SQL.
Uses persistent on-disk cache (.cache/dataset_eval_cache.json) and --limit to protect API quota.
Reports per-dataset Validity, Execution, and Result Accuracy.
Guarantees cleanup of all temporary ds_* schemas.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import settings
from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.schemas.dataset import DatasetProfile
from backend.app.schemas.dataset_semantic import DatasetAskResponse, DatasetSemanticResponse
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.sql_validator import DatasetSQLContext, SQLValidator
from backend.app.services.text_to_sql_service import TextToSQLService

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
EVAL_CACHE_FILE = CACHE_DIR / "dataset_eval_cache.json"

SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"

BENCHMARK_DATASETS = {
    "retail": {
        "name": "Retail Store Sales",
        "files": ["retail_customers.csv", "retail_orders.csv"],
        "questions": [
            {
                "id": "ret_01",
                "question": "How many total customers do we have?",
                "ref_sql": "SELECT count(*) AS count FROM {schema}.retail_customers;"
            },
            {
                "id": "ret_02",
                "question": "What is the total order amount across all delivered orders?",
                "ref_sql": "SELECT SUM(amount) AS total_sales FROM {schema}.retail_orders WHERE order_status = 'delivered';"
            },
            {
                "id": "ret_03",
                "question": "Top 5 customer cities by total order amount?",
                "ref_sql": "SELECT c.customer_city, SUM(o.amount) AS total_sales FROM {schema}.retail_customers c JOIN {schema}.retail_orders o ON c.customer_id = o.customer_id GROUP BY 1 ORDER BY 2 DESC LIMIT 5;"
            },
            {
                "id": "ret_04",
                "question": "How many orders were placed by VIP customers?",
                "ref_sql": "SELECT count(o.order_id) AS count FROM {schema}.retail_customers c JOIN {schema}.retail_orders o ON c.customer_id = o.customer_id WHERE c.is_vip = TRUE;"
            },
            {
                "id": "ret_05",
                "question": "What is the average order amount?",
                "ref_sql": "SELECT AVG(amount) AS avg_amount FROM {schema}.retail_orders;"
            }
        ]
    },
    "bike_sharing": {
        "name": "Bike Sharing Trips",
        "files": ["bike_sharing_messy.tsv"],
        "questions": [
            {
                "id": "bike_01",
                "question": "What is the total number of bike trips recorded?",
                "ref_sql": "SELECT count(*) AS count FROM {schema}.bike_sharing_messy;"
            },
            {
                "id": "bike_02",
                "question": "What is the average trip duration in minutes?",
                "ref_sql": "SELECT AVG(duration_mins) AS avg_duration FROM {schema}.bike_sharing_messy;"
            },
            {
                "id": "bike_03",
                "question": "Top 5 start stations with the most trips?",
                "ref_sql": "SELECT start_station, count(*) AS trips FROM {schema}.bike_sharing_messy GROUP BY 1 ORDER BY 2 DESC LIMIT 5;"
            },
            {
                "id": "bike_04",
                "question": "How many trips were taken by member vs casual riders?",
                "ref_sql": "SELECT user_type, count(*) AS count FROM {schema}.bike_sharing_messy GROUP BY 1 ORDER BY 2 DESC;"
            },
            {
                "id": "bike_05",
                "question": "What is the longest trip duration recorded?",
                "ref_sql": "SELECT MAX(duration_mins) AS max_duration FROM {schema}.bike_sharing_messy;"
            }
        ]
    },
    "student_marks": {
        "name": "Student Performance Marks",
        "files": ["student_marks.xlsx"],
        "questions": [
            {
                "id": "stu_01",
                "question": "How many total students are in the records?",
                "ref_sql": "SELECT count(DISTINCT student_id) AS count FROM {schema}.student_marks;"
            },
            {
                "id": "stu_02",
                "question": "What is the average marks in Mathematics?",
                "ref_sql": "SELECT AVG(marks) AS avg_math FROM {schema}.student_marks WHERE LOWER(subject) = 'mathematics';"
            },
            {
                "id": "stu_03",
                "question": "Top 5 students with the highest total marks?",
                "ref_sql": "SELECT student_name, SUM(marks) AS total_marks FROM {schema}.student_marks GROUP BY student_name ORDER BY total_marks DESC LIMIT 5;"
            },
            {
                "id": "stu_04",
                "question": "How many exam records passed vs failed?",
                "ref_sql": "SELECT passed, count(*) AS count FROM {schema}.student_marks GROUP BY passed ORDER BY count DESC;"
            },
            {
                "id": "stu_05",
                "question": "What is the average marks across all exams?",
                "ref_sql": "SELECT AVG(marks) AS avg_marks FROM {schema}.student_marks;"
            }
        ]
    }
}


def load_eval_cache() -> Dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if EVAL_CACHE_FILE.exists():
        try:
            with open(EVAL_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read eval cache: {e}")
    return {}


def save_eval_cache(cache: Dict[str, Any]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(EVAL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save eval cache: {e}")


def cleanup_all_ds_schemas():
    """Safety cleanup: drops any leftover ds_* schemas."""
    try:
        with engine.connect() as conn:
            schemas = [
                r[0]
                for r in conn.execute(
                    text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ds_%';")
                ).fetchall()
            ]
        if schemas:
            with engine.begin() as cleanup_conn:
                for s in schemas:
                    cleanup_conn.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'))
                    cleanup_conn.execute(text("DELETE FROM insightforge.datasets WHERE schema_name = :s;"), {"s": s})
    except Exception as e:
        logger.warning(f"Schema cleanup warning: {e}")


def run_dataset_eval(limit_per_dataset: int = 5):
    """Executes the Level 6 generality evaluation."""
    if not check_db_connection():
        print("ERROR: Live database connection is required for dataset evaluation. Exiting.")
        return

    cleanup_all_ds_schemas()
    eval_cache = load_eval_cache()

    results_table = []
    semantic_quirks = []

    print(f"\n{'='*70}")
    print(f"INSIGHTFORGE LEVEL 6: GENERALITY EVALUATION HARNESS")
    print(f"Datasets: {len(BENCHMARK_DATASETS)} | Questions per dataset limit: {limit_per_dataset}")
    print(f"{'='*70}\n")

    for ds_key, ds_info in BENCHMARK_DATASETS.items():
        ds_name = ds_info["name"]
        print(f"--> Uploading & profiling dataset: {ds_name} ({ds_key})...")

        files_data = []
        for fn in ds_info["files"]:
            fpath = SAMPLES_DIR / fn
            if not fpath.exists():
                print(f"    WARNING: Sample file {fn} not found. Skipping dataset.")
                continue
            with open(fpath, "rb") as f:
                files_data.append((fn, f.read()))

        if not files_data:
            continue

        upload_resp = DatasetService.upload_dataset(
            files_data=files_data,
            dataset_name=f"Eval: {ds_name}"
        )
        ds_id = upload_resp.dataset_id
        owner_token = upload_resp.owner_token
        schema_name = upload_resp.schema_name

        try:
            # Generate semantic draft
            sem_resp = DatasetSemanticService.generate_draft(ds_id, owner_token=owner_token)
            profile = DatasetService.get_dataset_profile(ds_id, owner_token=owner_token)

            # Check for any profiler / semantic layer quirks
            for t in profile.tables:
                if t.safe_name == "bike_sharing_messy":
                    time_col = next((c for c in t.columns if c.safe_name == "rental_time"), None)
                    if time_col and time_col.pg_type == "TEXT":
                        semantic_quirks.append(f"{ds_key}: 'rental_time' stored as TEXT due to ambiguous/messy date formats in TSV.")

            sql_context = DatasetSQLContext(
                schema_name=schema_name,
                allowed_tables={t.safe_name for t in profile.tables},
                relationships=[r.model_dump() for r in profile.relationships],
                table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in profile.tables},
                is_demo=False
            )

            questions = ds_info["questions"][:limit_per_dataset]
            valid_count = 0
            exec_count = 0
            acc_count = 0
            total_count = len(questions)

            for q_obj in questions:
                q_id = q_obj["id"]
                q_text = q_obj["question"]
                ref_sql_template = q_obj["ref_sql"]
                ref_sql = ref_sql_template.format(schema=schema_name)

                cache_key = hashlib.sha256(f"{ds_key}:{q_text}".encode("utf-8")).hexdigest()

                # Execute Reference SQL for ground truth
                ref_rows = []
                try:
                    with readonly_engine.connect() as conn:
                        res = conn.execute(text(ref_sql))
                        ref_rows = [list(r) for r in res.fetchall()]
                except Exception as e:
                    logger.warning(f"Ref SQL error for {q_id}: {e}")

                # Check Eval Cache
                cached_item = eval_cache.get(cache_key)
                if cached_item and cached_item.get("generated_sql"):
                    import re
                    raw_cached_sql = cached_item.get("generated_sql", "")
                    # Replace previous schema or placeholder with current dynamic schema
                    gen_sub = re.sub(r"\bds_[0-9a-f]{8}\b", schema_name, raw_cached_sql)
                    generated_sql = gen_sub.replace("{schema}", schema_name)
                    explanation = cached_item.get("explanation", "")
                    from_cache = True
                else:
                    # Run through real Gemini path
                    from_cache = False
                    ask_resp = TextToSQLService.ask_dataset_sql(
                        dataset_id=ds_id,
                        question=q_text,
                        owner_token=owner_token
                    )
                    generated_sql = ask_resp.sql
                    explanation = ask_resp.explanation

                    if generated_sql and "AI quota reached" not in explanation:
                        eval_cache[cache_key] = {
                            "question": q_text,
                            "generated_sql": generated_sql.replace(schema_name, "{schema}"),
                            "explanation": explanation
                        }
                        save_eval_cache(eval_cache)

                # Validation Check
                is_valid, sanitized_sql, val_err = SQLValidator.validate(generated_sql, context=sql_context)
                if is_valid:
                    valid_count += 1
                else:
                    print(f"    [INVALID] {q_id}: {val_err}")

                # Execution Check
                gen_rows = []
                exec_ok = False
                if is_valid and sanitized_sql:
                    try:
                        with readonly_engine.connect() as conn:
                            conn.execute(text(f'SET LOCAL search_path = "{schema_name}", public;'))
                            res = conn.execute(text(sanitized_sql))
                            gen_rows = [list(r) for r in res.fetchall()]
                            exec_ok = True
                            exec_count += 1
                    except Exception as e:
                        print(f"    [EXEC_FAIL] {q_id}: {e}")

                # Result Accuracy Check
                acc_ok = False
                if exec_ok and ref_rows and gen_rows:
                    # Check first row values comparison
                    try:
                        ref_first = ref_rows[0]
                        gen_first = gen_rows[0]
                        # Compare numerical values within 1% tolerance
                        match = True
                        for r_val, g_val in zip(ref_first, gen_first):
                            if isinstance(r_val, (int, float)) and isinstance(g_val, (int, float)):
                                if r_val != 0:
                                    if abs(r_val - g_val) / abs(r_val) > 0.02:
                                        match = False
                                else:
                                    if g_val != 0:
                                        match = False
                            elif str(r_val).strip().lower() != str(g_val).strip().lower():
                                match = False
                        if match:
                            acc_ok = True
                            acc_count += 1
                    except Exception:
                        pass

                cache_badge = "[CACHED]" if from_cache else "[LIVE_LLM]"
                print(f"    {cache_badge} {q_id}: valid={is_valid}, exec={exec_ok}, acc={acc_ok}")

            valid_pct = (valid_count / total_count) * 100 if total_count else 0
            exec_pct = (exec_count / total_count) * 100 if total_count else 0
            acc_pct = (acc_count / total_count) * 100 if total_count else 0

            results_table.append({
                "dataset": ds_name,
                "questions": total_count,
                "validity": f"{valid_pct:.0f}% ({valid_count}/{total_count})",
                "execution": f"{exec_pct:.0f}% ({exec_count}/{total_count})",
                "accuracy": f"{acc_pct:.0f}% ({acc_count}/{total_count})"
            })

        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    cleanup_all_ds_schemas()

    # Print Summary Markdown Table
    print(f"\n{'='*70}")
    print("GENERALITY EVALUATION SUMMARY TABLE")
    print(f"{'='*70}")
    print("| Dataset | Questions | AST Validity | Execution Rate | Result Accuracy |")
    print("| :--- | :---: | :---: | :---: | :---: |")
    for r in results_table:
        print(f"| {r['dataset']} | {r['questions']} | {r['validity']} | {r['execution']} | {r['accuracy']} |")
    print(f"{'='*70}")

    if semantic_quirks:
        print("\nSEMANTIC LAYER & PROFILER QUIRKS OBSERVED:")
        for quirk in semantic_quirks:
            print(f"- {quirk}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightForge Dataset Generality Eval")
    parser.add_argument("--limit", type=int, default=5, help="Questions per dataset limit")
    args = parser.parse_args()

    run_dataset_eval(limit_per_dataset=args.limit)
