import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import text
from psycopg2 import sql

from backend.app.config import settings
from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.schemas.dataset import UpdateDatasetRequest
from backend.app.services.dataset_service import DatasetService, hash_token
from scripts.cleanup_datasets import cleanup_expired_datasets

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "samples"


class TestDatasetsLiveIntegration(unittest.TestCase):
    """
    Live integration tests for Dataset Workspace on real PostgreSQL (Supabase).
    Verifies upload, COPY loading, deterministic profiling, schema isolation,
    readonly permissions, tenant isolation, preview, patching, and deletion.
    """

    @classmethod
    def setUpClass(cls):
        # Ensure not in fixture mode
        os.environ["USE_FIXTURES"] = "0"
        if not check_db_connection():
            raise unittest.SkipTest("Live PostgreSQL database is unreachable. Skipping live tests.")

    def test_01_upload_relational_dataset_and_profile(self):
        """Test uploading multi-file relational dataset (retail customers & orders)."""
        cust_path = SAMPLES_DIR / "retail_customers.csv"
        ord_path = SAMPLES_DIR / "retail_orders.csv"
        self.assertTrue(cust_path.exists())
        self.assertTrue(ord_path.exists())

        with open(cust_path, "rb") as f1, open(ord_path, "rb") as f2:
            files_data = [
                ("retail_customers.csv", f1.read()),
                ("retail_orders.csv", f2.read())
            ]

        # Ingest
        upload_resp = DatasetService.upload_dataset(
            files_data=files_data,
            owner_token=None,  # Issue new owner token
            dataset_name="Retail Store Demo"
        )

        self.assertIsNotNone(upload_resp.dataset_id)
        self.assertIsNotNone(upload_resp.owner_token)
        self.assertTrue(upload_resp.schema_name.startswith("ds_"))
        self.assertEqual(upload_resp.tables_count, 2)
        self.assertEqual(upload_resp.total_rows, 400)  # 100 customers + 300 orders

        ds_id = upload_resp.dataset_id
        owner_token = upload_resp.owner_token
        schema_name = upload_resp.schema_name

        try:
            # 1. Fetch Profile
            profile = DatasetService.get_dataset_profile(ds_id, owner_token=owner_token)
            self.assertEqual(len(profile.tables), 2)
            self.assertEqual(profile.name, "Retail Store Demo")

            table_names = {t.safe_name for t in profile.tables}
            self.assertIn("retail_customers", table_names)
            self.assertIn("retail_orders", table_names)

            # Check Relationship Inference
            self.assertGreaterEqual(len(profile.relationships), 1)
            rel = profile.relationships[0]
            self.assertEqual(rel.parent_table, "retail_customers")
            self.assertEqual(rel.parent_column, "customer_id")
            self.assertEqual(rel.child_table, "retail_orders")
            self.assertEqual(rel.child_column, "customer_id")
            self.assertEqual(rel.cardinality, "1:N")

            # 2. Preview via readonly_engine
            preview = DatasetService.preview_table(ds_id, "retail_orders", limit=10, owner_token=owner_token)
            self.assertEqual(preview.preview_rows_count, 10)
            self.assertEqual(preview.total_rows, 300)
            self.assertIn("order_id", preview.columns)
            self.assertIn("amount", preview.columns)

            # 3. Security Check: insightforge_ro CAN SELECT from dynamic schema
            with readonly_engine.connect() as ro_conn:
                cnt = ro_conn.execute(
                    text(f'SELECT count(*) FROM "{schema_name}"."retail_orders";')
                ).scalar()
                self.assertEqual(cnt, 300)

            # 4. Security Check: insightforge_ro CANNOT access metadata tables
            with readonly_engine.connect() as ro_conn:
                with self.assertRaises(Exception) as ctx:
                    ro_conn.execute(text("SELECT count(*) FROM insightforge.datasets;"))
                self.assertIn("permission denied", str(ctx.exception).lower())

            # 5. Tenant Isolation: Wrong owner token fails
            from backend.app.services.dataset_file_parser import FileValidationError
            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.get_dataset_profile(ds_id, owner_token="wrong_token_12345")
            self.assertEqual(ctx.exception.status_code, 403)

            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.delete_dataset(ds_id, owner_token="wrong_token_12345")
            self.assertEqual(ctx.exception.status_code, 403)

            # 6. Update Column Description & Confirm Relationship
            updated_profile = DatasetService.update_dataset(
                dataset_id=ds_id,
                req=UpdateDatasetRequest(
                    column_updates=[{
                        "table_name": "retail_orders",
                        "column_name": "amount",
                        "role": "measure",
                        "user_description": "Gross order amount in BRL"
                    }],
                    confirmed_relationships=[{
                        "parent_table": "retail_customers",
                        "parent_column": "customer_id",
                        "child_table": "retail_orders",
                        "child_column": "customer_id",
                        "confirmed": True
                    }]
                ),
                owner_token=owner_token
            )
            # Verify update took effect
            orders_tbl = next(t for t in updated_profile.tables if t.safe_name == "retail_orders")
            amount_col = next(c for c in orders_tbl.columns if c.safe_name == "amount")
            self.assertEqual(amount_col.user_description, "Gross order amount in BRL")
            self.assertTrue(updated_profile.relationships[0].confirmed)

        finally:
            # 7. Delete dataset and verify schema dropped
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

            # Verify schema is gone in PostgreSQL
            with engine.connect() as conn:
                schema_exists = conn.execute(
                    text("SELECT exists(SELECT 1 FROM information_schema.schemata WHERE schema_name = :s);"),
                    {"s": schema_name}
                ).scalar()
                self.assertFalse(schema_exists)

    def test_02_upload_excel_dataset(self):
        """Test uploading Excel (.xlsx) dataset."""
        marks_path = SAMPLES_DIR / "student_marks.xlsx"
        self.assertTrue(marks_path.exists())

        with open(marks_path, "rb") as f:
            files_data = [("student_marks.xlsx", f.read())]

        resp = DatasetService.upload_dataset(files_data=files_data, dataset_name="Student Exam Results")
        ds_id = resp.dataset_id
        owner_token = resp.owner_token
        schema_name = resp.schema_name

        try:
            self.assertEqual(resp.tables_count, 1)
            self.assertEqual(resp.total_rows, 250)

            # Preview
            preview = DatasetService.preview_table(ds_id, "student_marks", limit=5, owner_token=owner_token)
            self.assertEqual(preview.preview_rows_count, 5)
            self.assertIn("student_id", preview.columns)
            self.assertIn("marks", preview.columns)
        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_03_upload_messy_tsv_dataset(self):
        """Test uploading messy TSV with ambiguous dates, constant column, and high nulls."""
        messy_path = SAMPLES_DIR / "bike_sharing_messy.tsv"
        self.assertTrue(messy_path.exists())

        with open(messy_path, "rb") as f:
            files_data = [("bike_sharing_messy.tsv", f.read())]

        resp = DatasetService.upload_dataset(files_data=files_data, dataset_name="Bike Sharing Messy")
        ds_id = resp.dataset_id
        owner_token = resp.owner_token

        try:
            profile = DatasetService.get_dataset_profile(ds_id, owner_token=owner_token)
            tbl = profile.tables[0]
            findings = [f["type"] for f in tbl.quality_findings]

            # Quality findings must detect constant column and high nulls
            self.assertIn("constant_column", findings)
            self.assertIn("high_null_column", findings)
        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_04_cleanup_expired_datasets(self):
        """Test automatic cleanup of expired datasets."""
        # Create a dummy dataset with expires_at in the past
        files_data = [("test_dummy.csv", b"id,val\n1,100\n2,200\n")]
        resp = DatasetService.upload_dataset(files_data=files_data, dataset_name="Expired Dataset")
        ds_id = resp.dataset_id
        schema_name = resp.schema_name

        # Force expires_at to 1 hour ago
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE insightforge.datasets SET expires_at = NOW() - INTERVAL '1 hour' WHERE id = :id;"),
                {"id": ds_id}
            )

        # Run cleanup
        purged = cleanup_expired_datasets(dry_run=False)
        self.assertGreaterEqual(purged, 1)

        # Verify schema dropped
        with engine.connect() as conn:
            schema_exists = conn.execute(
                text("SELECT exists(SELECT 1 FROM information_schema.schemata WHERE schema_name = :s);"),
                {"s": schema_name}
            ).scalar()
            self.assertFalse(schema_exists)


if __name__ == "__main__":
    unittest.main()
