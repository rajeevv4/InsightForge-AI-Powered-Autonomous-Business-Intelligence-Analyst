import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from psycopg2 import sql
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.config import settings
from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_service import DatasetService
from scripts.cleanup_datasets import cleanup_expired_datasets


class TestDatasetIsolationAndSecurityLive(unittest.TestCase):
    """
    Live PostgreSQL integration tests for tenant isolation, security barriers,
    atomic failure rollback, quota enforcement, and cleanup.
    """

    created_dataset_ids = []

    @classmethod
    def setUpClass(cls):
        os.environ["USE_FIXTURES"] = "0"
        if not check_db_connection():
            raise unittest.SkipTest("Live PostgreSQL database is unreachable. Skipping live tests.")

    @classmethod
    def tearDownClass(cls):
        """Ensure all created test datasets are purged and no ds_* schemas remain."""
        for ds_id in cls.created_dataset_ids:
            try:
                with engine.begin() as conn:
                    row = conn.execute(
                        text("SELECT schema_name FROM insightforge.datasets WHERE id = :id"),
                        {"id": ds_id}
                    ).fetchone()
                    if row:
                        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(row[0])))
                    conn.execute(text("DELETE FROM insightforge.datasets WHERE id = :id"), {"id": ds_id})
            except Exception:
                pass

        cleanup_expired_datasets(dry_run=False)

        # Verify no test schemas remain
        with engine.connect() as conn:
            rem = conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'ds_%';")
            ).fetchall()
            if rem:
                for r in rem:
                    with engine.begin() as c2:
                        c2.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(r[0])))

    def test_tenant_isolation_owner_b_forbidden(self):
        """Owner A's dataset cannot be viewed, patched, previewed, or deleted by Owner B."""
        files = [("orders.csv", b"order_id,amount\nORD_1,150.0\nORD_2,250.0\n")]
        resp = DatasetService.upload_dataset(files_data=files, dataset_name="Tenant Isolation Test")
        ds_id = resp.dataset_id
        owner_a_token = resp.owner_token
        self.__class__.created_dataset_ids.append(ds_id)

        owner_b_token = "invalid_token_from_owner_b"

        # 1. GET profile with Owner B token -> 403
        with self.assertRaises(FileValidationError) as ctx:
            DatasetService.get_dataset_profile(ds_id, owner_token=owner_b_token)
        self.assertEqual(ctx.exception.status_code, 403)

        # 2. Preview with Owner B token -> 403
        with self.assertRaises(FileValidationError) as ctx:
            DatasetService.preview_table(ds_id, "orders", owner_token=owner_b_token)
        self.assertEqual(ctx.exception.status_code, 403)

        # 3. DELETE with Owner B token -> 403
        with self.assertRaises(FileValidationError) as ctx:
            DatasetService.delete_dataset(ds_id, owner_token=owner_b_token)
        self.assertEqual(ctx.exception.status_code, 403)

        # Clean up with Owner A token
        DatasetService.delete_dataset(ds_id, owner_token=owner_a_token)

    def test_unauthenticated_access_forbidden(self):
        """Accessing private dataset without owner_token raises 403."""
        files = [("data.csv", b"x,y\n1,2\n")]
        resp = DatasetService.upload_dataset(files_data=files, dataset_name="Private Dataset")
        ds_id = resp.dataset_id
        owner_token = resp.owner_token
        self.__class__.created_dataset_ids.append(ds_id)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.get_dataset_profile(ds_id, owner_token=None)
            self.assertEqual(ctx.exception.status_code, 403)
        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_guessed_dataset_id_returns_404(self):
        """Accessing random non-existent UUID returns 404."""
        random_uuid = "11111111-2222-3333-4444-555555555555"
        with self.assertRaises(FileValidationError) as ctx:
            DatasetService.get_dataset_profile(random_uuid, owner_token="some_token")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_preview_invalid_table_param_returns_404(self):
        """Requesting preview for table not in dataset's registered tables returns 404."""
        files = [("metrics.csv", b"metric,val\nm1,10\n")]
        resp = DatasetService.upload_dataset(files_data=files, dataset_name="Table Validation Test")
        ds_id = resp.dataset_id
        owner_token = resp.owner_token
        self.__class__.created_dataset_ids.append(ds_id)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.preview_table(ds_id, "non_existent_table", owner_token=owner_token)
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertIn("not found", str(ctx.exception))
        finally:
            DatasetService.delete_dataset(ds_id, owner_token=owner_token)

    def test_readonly_user_cannot_read_metadata(self):
        """insightforge_ro role has NO SELECT permissions on metadata tables."""
        raw_conn = readonly_engine.raw_connection()
        try:
            with raw_conn.cursor() as cur:
                with self.assertRaises(Exception) as ctx:
                    cur.execute("SELECT * FROM insightforge.datasets LIMIT 1;")
                self.assertIn("permission denied", str(ctx.exception).lower())
        finally:
            raw_conn.close()

    def test_olist_demo_cannot_be_deleted(self):
        """Attempting to delete olist-demo returns 403."""
        demo_id = "00000000-0000-0000-0000-000000000001"
        with self.assertRaises(FileValidationError) as ctx:
            DatasetService.delete_dataset(demo_id, owner_token="any_token")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("built-in demo dataset cannot be deleted", str(ctx.exception))

    def test_failure_atomicity_leaves_no_schema(self):
        """When an upload fails midway, transaction rollback leaves no schema and no metadata rows."""
        files = [
            ("valid_table.csv", b"id,val\n1,100\n"),
            ("bad_table.csv", b"%PDF-1.4 disguised invalid content")
        ]
        with self.assertRaises(FileValidationError):
            DatasetService.upload_dataset(files_data=files, dataset_name="Atomicity Test")

        with engine.connect() as conn:
            orphan_ds = conn.execute(
                text("SELECT id, schema_name FROM insightforge.datasets WHERE name = 'Atomicity Test';")
            ).fetchall()
            self.assertEqual(len(orphan_ds), 0)

    def test_quota_max_datasets_per_owner(self):
        """An owner cannot exceed MAX_DATASETS_PER_OWNER active datasets."""
        fixed_token = "quota_test_owner_token_abc123"
        created = []
        try:
            for i in range(settings.MAX_DATASETS_PER_OWNER):
                r = DatasetService.upload_dataset(
                    files_data=[(f"t_{i}.csv", b"a,b\n1,2\n")],
                    owner_token=fixed_token,
                    dataset_name=f"Quota Test {i}"
                )
                created.append(r.dataset_id)
                self.__class__.created_dataset_ids.append(r.dataset_id)

            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.upload_dataset(
                    files_data=[("overflow.csv", b"a,b\n1,2\n")],
                    owner_token=fixed_token,
                    dataset_name="Quota Overflow"
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertTrue(
                "quota" in str(ctx.exception).lower() or "limit" in str(ctx.exception).lower() or "maximum" in str(ctx.exception).lower(),
                f"Unexpected exception message: {ctx.exception}"
            )
        finally:
            for ds_id in created:
                try:
                    DatasetService.delete_dataset(ds_id, owner_token=fixed_token)
                except Exception:
                    pass

    def test_db_size_guard_returns_507(self):
        """When database storage exceeds MAX_TOTAL_DB_MB, uploads are rejected with 507."""
        with patch("backend.app.services.dataset_service.DatasetService.check_database_storage_capacity") as mock_guard:
            mock_guard.side_effect = FileValidationError(
                f"Database storage threshold of {settings.MAX_TOTAL_DB_MB} MB exceeded.",
                status_code=507
            )
            with self.assertRaises(FileValidationError) as ctx:
                DatasetService.upload_dataset(
                    files_data=[("test.csv", b"a,b\n1,2\n")],
                    dataset_name="Storage Guard Test"
                )
            self.assertEqual(ctx.exception.status_code, 507)


if __name__ == "__main__":
    unittest.main()
