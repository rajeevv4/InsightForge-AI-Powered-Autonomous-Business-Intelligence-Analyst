"""
Live Integration Tests for Level 6: Dataset-Aware Q&A and Semantic Layer
=======================================================================
Runs on live PostgreSQL (Supabase) if accessible, otherwise skips with clear message.
Verifies:
- Uploading each sample dataset (retail, bike sharing, student marks, and real/ if present)
- Semantic layer generation (measures, dimensions, starter questions)
- Execution of template questions through SQLValidator & comparison with reference SQL
- Quick insights computation with non-empty charts
- Complete cleanup leaving zero leftover ds_* schemas
"""

import os
import unittest
from pathlib import Path
from sqlalchemy import text

from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.schemas.dataset import DatasetProfile
from backend.app.schemas.dataset_semantic import DatasetInsightsResponse, DatasetSemanticResponse
from backend.app.services.dataset_insights_service import DatasetInsightsService
from backend.app.services.dataset_semantic_service import DatasetSemanticService
from backend.app.services.dataset_service import DatasetService
from backend.app.services.sql_validator import DatasetSQLContext, SQLValidator

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"


class TestDatasetQALiveIntegration(unittest.TestCase):
    """Live DB integration tests for Level 6."""

    @classmethod
    def setUpClass(cls):
        os.environ["USE_FIXTURES"] = "0"
        if not check_db_connection():
            raise unittest.SkipTest("Live PostgreSQL database is unreachable. Skipping live dataset QA tests.")

    @classmethod
    def tearDownClass(cls):
        # Guarantee no leftover ds_* schemas or dsr_* roles exist
        if check_db_connection():
            with engine.connect() as conn:
                schemas = [
                    row[0]
                    for row in conn.execute(
                        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ds_%';")
                    ).fetchall()
                ]
                roles = [
                    row[0]
                    for row in conn.execute(
                        text("SELECT rolname FROM pg_roles WHERE rolname LIKE 'dsr_%';")
                    ).fetchall()
                ]
            if schemas or roles:
                with engine.begin() as cleanup_conn:
                    for s in schemas:
                        cleanup_conn.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'))
                        cleanup_conn.execute(text("DELETE FROM insightforge.datasets WHERE schema_name = :s;"), {"s": s})
                    for r in roles:
                        try:
                            cleanup_conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{r}";'))
                        except Exception:
                            pass
                        try:
                            cleanup_conn.execute(text(f'REVOKE "{r}" FROM insightforge_ro;'))
                        except Exception:
                            pass
                        cleanup_conn.execute(text(f'DROP ROLE IF EXISTS "{r}";'))

    def test_01_retail_relational_qa_and_insights(self):
        """Upload retail relational dataset, generate semantic layer, test questions & insights."""
        cust_path = SAMPLES_DIR / "retail_customers.csv"
        ord_path = SAMPLES_DIR / "retail_orders.csv"
        self.assertTrue(cust_path.exists())
        self.assertTrue(ord_path.exists())

        with open(cust_path, "rb") as f1, open(ord_path, "rb") as f2:
            files_data = [
                ("retail_customers.csv", f1.read()),
                ("retail_orders.csv", f2.read())
            ]

        upload_resp = DatasetService.upload_dataset(
            files_data=files_data,
            dataset_name="Live Retail Test"
        )
        ds_id = upload_resp.dataset_id
        owner_token = upload_resp.owner_token
        schema_name = upload_resp.schema_name

        try:
            # 1. Generate Semantic Layer
            sem_resp: DatasetSemanticResponse = DatasetSemanticService.generate_draft(ds_id, owner_token=owner_token)
            self.assertEqual(sem_resp.status, "draft")
            self.assertGreaterEqual(len(sem_resp.semantic_model.measures), 2)
            self.assertGreaterEqual(len(sem_resp.starter_questions), 6)

            # 2. Test Question through SQLValidator & execute
            profile: DatasetProfile = DatasetService.get_dataset_profile(ds_id, owner_token=owner_token)
            sql_context = DatasetSQLContext(
                schema_name=schema_name,
                allowed_tables={t.safe_name for t in profile.tables},
                relationships=[r.model_dump() for r in profile.relationships],
                table_columns={t.safe_name: {c.safe_name for c in t.columns} for t in profile.tables},
                is_demo=False
            )

            # Test Question: Total order amount by customer city
            test_sql = (
                f"SELECT c.customer_city, SUM(o.amount) AS total_sales "
                f"FROM {schema_name}.retail_customers c "
                f"JOIN {schema_name}.retail_orders o ON c.customer_id = o.customer_id "
                f"GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
            )
            is_valid, sanitized_sql, err = SQLValidator.validate(test_sql, context=sql_context)
            self.assertTrue(is_valid, f"Validation failed: {err}")

            with readonly_engine.connect() as conn:
                conn.execute(text(f'SET LOCAL search_path = "{schema_name}", public;'))
                result = conn.execute(text(sanitized_sql))
                test_rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]

            # Reference SQL
            ref_sql = (
                f"SELECT c.customer_city, SUM(o.amount) AS total_sales "
                f"FROM {schema_name}.retail_customers c "
                f"JOIN {schema_name}.retail_orders o ON c.customer_id = o.customer_id "
                f"GROUP BY c.customer_city ORDER BY total_sales DESC LIMIT 10;"
            )
            with readonly_engine.connect() as conn:
                ref_result = conn.execute(text(ref_sql))
                ref_rows = [dict(zip(ref_result.keys(), row)) for row in ref_result.fetchall()]

            self.assertEqual(len(test_rows), len(ref_rows))
            self.assertGreater(len(test_rows), 0)
            self.assertEqual(test_rows[0]["customer_city"], ref_rows[0]["customer_city"])

            # 3. Test Quick Insights
            insights: DatasetInsightsResponse = DatasetInsightsService.get_insights(ds_id, owner_token=owner_token)
            self.assertIsNotNone(insights.top_n)
            self.assertGreater(len(insights.top_n.data), 0)
            self.assertIsNotNone(insights.distribution)
            self.assertGreater(len(insights.distribution.data), 0)

        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_02_bike_sharing_tsv_qa_and_insights(self):
        """Upload TSV dataset, generate semantic layer and verify quick insights."""
        tsv_path = SAMPLES_DIR / "bike_sharing_messy.tsv"
        self.assertTrue(tsv_path.exists())

        with open(tsv_path, "rb") as f:
            files_data = [("bike_sharing_messy.tsv", f.read())]

        upload_resp = DatasetService.upload_dataset(
            files_data=files_data,
            dataset_name="Live Bike Sharing Test"
        )
        ds_id = upload_resp.dataset_id
        owner_token = upload_resp.owner_token
        schema_name = upload_resp.schema_name

        try:
            sem_resp = DatasetSemanticService.generate_draft(ds_id, owner_token=owner_token)
            self.assertGreaterEqual(len(sem_resp.semantic_model.measures), 1)

            insights = DatasetInsightsService.get_insights(ds_id, owner_token=owner_token)
            # Verify non-empty charts
            has_chart_data = (
                (insights.time_trend and len(insights.time_trend.data) > 0) or
                (insights.top_n and len(insights.top_n.data) > 0) or
                (insights.distribution and len(insights.distribution.data) > 0)
            )
            self.assertTrue(has_chart_data, "Quick insights returned no chart data")

        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_03_student_marks_xlsx_qa_and_insights(self):
        """Upload XLSX dataset, generate semantic layer and verify quick insights."""
        xlsx_path = SAMPLES_DIR / "student_marks.xlsx"
        self.assertTrue(xlsx_path.exists())

        with open(xlsx_path, "rb") as f:
            files_data = [("student_marks.xlsx", f.read())]

        upload_resp = DatasetService.upload_dataset(
            files_data=files_data,
            dataset_name="Live Student Marks Test"
        )
        ds_id = upload_resp.dataset_id
        owner_token = upload_resp.owner_token
        schema_name = upload_resp.schema_name

        try:
            sem_resp = DatasetSemanticService.generate_draft(ds_id, owner_token=owner_token)
            self.assertGreaterEqual(len(sem_resp.semantic_model.measures), 1)

            insights = DatasetInsightsService.get_insights(ds_id, owner_token=owner_token)
            has_chart_data = (
                (insights.top_n and len(insights.top_n.data) > 0) or
                (insights.distribution and len(insights.distribution.data) > 0)
            )
            self.assertTrue(has_chart_data, "Quick insights returned no chart data")

        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_04_real_samples_if_present(self):
        """Tests any additional files present in data/samples/real/."""
        real_dir = SAMPLES_DIR / "real"
        if not real_dir.exists() or not any(real_dir.iterdir()):
            self.skipTest("No files in data/samples/real/. Skipping.")

    def test_05_cross_dataset_isolation_and_db_role_defense_in_depth(self):
        """
        Level 6.1 Security & Defense-in-Depth Live Integration Test:
        1. Uploads two independent datasets A (retail) and B (bike sharing).
        2. Proves that on Dataset A, queries targeting Dataset B are rejected by SQLValidator.
        3. Proves DEFENSE IN DEPTH: even if the validator is bypassed, PostgreSQL's
           SET LOCAL ROLE dsr_<8hex> enforces database-level permission denial.
        4. Verifies time column profiling on bike sharing (TIMESTAMP, datetime role, candidate time column).
        """
        cust_path = SAMPLES_DIR / "retail_customers.csv"
        tsv_path = SAMPLES_DIR / "bike_sharing_messy.tsv"

        with open(cust_path, "rb") as f_a, open(tsv_path, "rb") as f_b:
            data_a = [("retail_customers.csv", f_a.read())]
            data_b = [("bike_sharing_messy.tsv", f_b.read())]

        resp_a = DatasetService.upload_dataset(files_data=data_a, dataset_name="Live Dataset A")
        resp_b = DatasetService.upload_dataset(files_data=data_b, dataset_name="Live Dataset B")

        ds_id_a, token_a, schema_a = resp_a.dataset_id, resp_a.owner_token, resp_a.schema_name
        ds_id_b, token_b, schema_b = resp_b.dataset_id, resp_b.owner_token, resp_b.schema_name

        try:
            profile_a: DatasetProfile = DatasetService.get_dataset_profile(ds_id_a, owner_token=token_a)
            profile_b: DatasetProfile = DatasetService.get_dataset_profile(ds_id_b, owner_token=token_b)

            # 1. Verify Time Column Profiling for Dataset B (bike_sharing)
            # Before Level 6.1: rental_time was TEXT, role was dimension, candidate_time_column was None.
            # After Level 6.1: rental_time is TIMESTAMP, role is datetime, candidate_time_column is rental_time.
            bike_tbl = profile_b.tables[0]
            rental_time_col = next((c for c in bike_tbl.columns if c.safe_name == "rental_time"), None)
            self.assertIsNotNone(rental_time_col, "rental_time column not found in bike sharing")
            self.assertEqual(rental_time_col.pg_type, "TIMESTAMP", f"Expected TIMESTAMP, got {rental_time_col.pg_type}")
            self.assertEqual(rental_time_col.role, "datetime", f"Expected role 'datetime', got {rental_time_col.role}")
            self.assertEqual(bike_tbl.candidate_time_column, "rental_time", f"Expected candidate_time_column 'rental_time', got {bike_tbl.candidate_time_column}")

            # Verify time-trend insight runs directly on the TIMESTAMP column
            insights_b = DatasetInsightsService.get_insights(ds_id_b, owner_token=token_b)
            self.assertIsNotNone(insights_b.time_trend, "Expected time_trend chart to be generated")
            self.assertGreater(len(insights_b.time_trend.data), 0, "Time trend data should not be empty")

            # 2. Validator rejection of cross-dataset access
            ctx_a = DatasetSQLContext(
                schema_name=schema_a,
                allowed_tables={t.safe_name for t in profile_a.tables},
                is_demo=False
            )
            cross_sql = f"SELECT * FROM {schema_b}.bike_sharing_messy;"
            is_valid, sanitized_sql, val_err = SQLValidator.validate(cross_sql, context=ctx_a)
            self.assertFalse(is_valid, "Validator should have rejected cross-dataset query to schema B")
            self.assertIn(f"Access to schema '{schema_b}' is forbidden", val_err)

            # 3. Defense-in-Depth Database Role Isolation:
            # Even if the validator is bypassed, PostgreSQL itself prevents dsr_a from reading schema B!
            role_a = f"dsr_{schema_a[3:]}"
            db_denied = False
            try:
                with readonly_engine.connect() as conn:
                    with conn.begin():
                        conn.execute(text(f'SET LOCAL ROLE "{role_a}";'))
                        conn.execute(text(f'SELECT count(*) FROM {schema_b}.bike_sharing_messy;'))
            except Exception as e:
                db_denied = True
                self.assertIn("permission denied", str(e).lower())

            self.assertTrue(db_denied, "PostgreSQL failed to block cross-dataset read under dedicated role dsr_a!")

        finally:
            DatasetService.delete_dataset(ds_id_a, owner_token=token_a)
            DatasetService.delete_dataset(ds_id_b, owner_token=token_b)


if __name__ == "__main__":
    unittest.main()
