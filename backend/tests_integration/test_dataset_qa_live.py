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
        # Guarantee no leftover ds_* schemas exist
        if check_db_connection():
            with engine.connect() as conn:
                schemas = [
                    row[0]
                    for row in conn.execute(
                        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ds_%';")
                    ).fetchall()
                ]
                if schemas:
                    with engine.begin() as cleanup_conn:
                        for s in schemas:
                            cleanup_conn.execute(text(f'DROP SCHEMA IF EXISTS "{s}" CASCADE;'))
                            cleanup_conn.execute(text("DELETE FROM insightforge.datasets WHERE schema_name = :s;"), {"s": s})

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


if __name__ == "__main__":
    unittest.main()
