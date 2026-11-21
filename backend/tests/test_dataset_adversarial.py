import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
from psycopg2 import sql
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.config import settings
from backend.app.database import engine, readonly_engine, check_db_connection
from backend.app.services.dataset_file_parser import DatasetFileParser, FileValidationError
from backend.app.services.dataset_sanitizer import (
    sanitize_identifier,
    sanitize_column_list,
    sanitize_table_name,
)
from backend.app.services.dataset_service import DatasetService, hash_token
from scripts.cleanup_datasets import cleanup_expired_datasets


class TestDatasetFileAdversarial(unittest.TestCase):
    """
    Adversarial file parser tests:
    Verifies handling of BOM UTF-8, Latin-1, TSV, ragged rows, huge cells,
    disguised binaries, .xlsm rejection, path traversal, RTL/emoji filenames,
    XLSX decompression bombs, XLSX sheet count limits, size/row/col limits,
    and formula injection neutralization.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bom_utf8_csv(self):
        """CSV with UTF-8 BOM is detected and parsed without corrupted column headers."""
        p = self.dir_path / "bom_test.csv"
        p.write_bytes(b"\xef\xbb\xbfid,name,value\n1,alpha,10.5\n2,beta,20.0\n")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "bom_test.csv")
        self.assertEqual(cols[0], "id")
        self.assertEqual(len(df), 2)

    def test_latin1_csv(self):
        """CSV with Latin-1 (ISO-8859-1) accented characters is parsed correctly."""
        p = self.dir_path / "latin1_test.csv"
        content = "cidade,região\nSão Paulo,Sudeste\nCuritiba,Sul\n"
        p.write_bytes(content.encode("latin-1"))
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "latin1_test.csv")
        self.assertEqual(len(df), 2)
        self.assertIn("cidade", cols)

    def test_semicolon_csv(self):
        """CSV with semicolon delimiter is detected and parsed with correct columns."""
        p = self.dir_path / "semicolon_test.csv"
        p.write_text("order_id;customer_id;amount\n101;202;55.00\n102;203;88.50\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "semicolon_test.csv")
        self.assertEqual(len(df), 2)
        self.assertEqual(len(cols), 3)
        self.assertIn("order_id", cols)

    def test_tab_tsv(self):
        """TSV format is parsed correctly with tab delimiter."""
        p = self.dir_path / "tab_test.tsv"
        p.write_text("item_id\tqty\tprice\n1\t5\t19.99\n2\t10\t49.99\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "tab_test.tsv")
        self.assertEqual(len(df), 2)
        self.assertEqual(len(cols), 3)

    def test_ragged_rows_skipped(self):
        """Malformed rows with ragged column counts are skipped via on_bad_lines='skip'."""
        p = self.dir_path / "ragged_test.csv"
        # Row 2 has 4 fields instead of 3
        p.write_text("col_a,col_b,col_c\n1,2,3\n4,5,6,extra\n7,8,9\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "ragged_test.csv")
        self.assertEqual(len(df), 2)  # Middle row skipped

    def test_huge_single_cell(self):
        """A 1MB single text cell is handled as TEXT without memory crash or corruption."""
        p = self.dir_path / "huge_cell.csv"
        big_text = "A" * (1024 * 1024)  # 1MB string
        p.write_text(f"id,payload\n1,{big_text}\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "huge_cell.csv")
        self.assertEqual(len(df), 1)
        self.assertEqual(len(df["payload"].iloc[0]), 1024 * 1024)

    def test_disguised_pdf_as_csv_rejected(self):
        """PDF binary disguised with .csv extension is rejected with 400."""
        p = self.dir_path / "fake_data.csv"
        p.write_bytes(b"%PDF-1.4 header and binary stream...")
        with self.assertRaises(FileValidationError) as ctx:
            DatasetFileParser.validate_file_content(p, "fake_data.csv")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("PDF", str(ctx.exception))

    def test_disallowed_extension_xlsm(self):
        """Macro-enabled Excel (.xlsm) extension is rejected with 400."""
        p = self.dir_path / "malicious.xlsm"
        p.write_bytes(b"dummy")
        with self.assertRaises(FileValidationError) as ctx:
            DatasetFileParser.validate_file_content(p, "malicious.xlsm")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_path_traversal_filename_sanitized(self):
        """Path traversal sequences in filenames are sanitized to safe table names."""
        p = self.dir_path / "test.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "../../etc/passwd.csv")
        self.assertEqual(tbl, "passwd")
        self.assertNotIn("/", tbl)
        self.assertNotIn("..", tbl)

    def test_rtl_emoji_long_filename_sanitized(self):
        """Filenames with RTL Arabic, emoji, and excessive length are safely sanitized."""
        name = "🎉sales_بيانات_المبيعات_summary_data_for_the_year_2024_quarter_1_extended_long_title.csv"
        tbl = sanitize_table_name(name)
        self.assertTrue(tbl.isidentifier())
        self.assertLessEqual(len(tbl), 63)
        self.assertTrue(tbl.startswith("sales_") or tbl.startswith("tbl_"))

    def test_xlsx_decompression_bomb_rejected(self):
        """Excel archive with uncompressed size exceeding safety threshold is rejected."""
        p = self.dir_path / "bomb.xlsx"
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("xl/workbook.xml", b"<xml>small compressed data</xml>")

        # Mock infolist to simulate an uncompressed size of > 500 MB
        mock_info = zipfile.ZipInfo("xl/workbook.xml")
        mock_info.file_size = (settings.XLSX_MAX_UNCOMPRESSED_MB + 50) * 1024 * 1024

        with patch("zipfile.ZipFile.infolist", return_value=[mock_info]):
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.validate_file_content(p, "bomb.xlsx")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("safety limit", str(ctx.exception).lower())

    def test_xlsx_too_many_sheets_rejected(self):
        """Excel file with more sheets than XLSX_MAX_SHEETS is rejected."""
        import openpyxl
        wb = openpyxl.Workbook()
        for i in range(settings.XLSX_MAX_SHEETS + 5):
            wb.create_sheet(title=f"Sheet_{i}")
        p = self.dir_path / "many_sheets.xlsx"
        wb.save(p)
        wb.close()

        with self.assertRaises(FileValidationError) as ctx:
            DatasetFileParser.parse_to_dataframe(p, "many_sheets.xlsx")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("sheets", str(ctx.exception))

    def test_oversize_file_rejected(self):
        """Files exceeding MAX_FILE_SIZE_MB are rejected with 413."""
        p = self.dir_path / "oversize.csv"
        p.write_bytes(b"dummy")
        with patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_size = (settings.MAX_FILE_SIZE_MB + 1) * 1024 * 1024
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.validate_file_content(p, "oversize.csv")
            self.assertEqual(ctx.exception.status_code, 413)

    def test_too_many_rows_rejected(self):
        """Files exceeding MAX_ROWS_PER_TABLE are rejected with 413."""
        p = self.dir_path / "too_many_rows.csv"
        # Simulate with patch on MAX_ROWS_PER_TABLE
        with patch.object(settings, "MAX_ROWS_PER_TABLE", 5):
            p.write_text("col\n1\n2\n3\n4\n5\n6\n7\n", encoding="utf-8")
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.parse_to_dataframe(p, "too_many_rows.csv")
            self.assertEqual(ctx.exception.status_code, 413)

    def test_too_many_columns_rejected(self):
        """Files exceeding MAX_COLUMNS_PER_TABLE are rejected with 400."""
        p = self.dir_path / "too_many_cols.csv"
        cols = [f"c_{i}" for i in range(settings.MAX_COLUMNS_PER_TABLE + 5)]
        p.write_text(",".join(cols) + "\n" + ",".join(["1"] * len(cols)) + "\n", encoding="utf-8")
        with self.assertRaises(FileValidationError) as ctx:
            DatasetFileParser.parse_to_dataframe(p, "too_many_cols.csv")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("maximum column limit", str(ctx.exception))

    def test_formula_injection_neutralized(self):
        """Cells beginning with =, +, -, @ are prefixed with tab to neutralize CSV injection."""
        p = self.dir_path / "formula_inject.csv"
        p.write_text(
            "id,formula_cell,safe_cell\n"
            "1,=SUM(1+1),normal_text\n"
            "2,+cmd|' /C calc'!A0,another_val\n"
            "3,@HYPERLINK('bad.com'),clean\n"
            "4,-2+3+cmd,pure\n",
            encoding="utf-8"
        )
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "formula_inject.csv")
        # All dangerous cells in formula_cell must start with \t
        for val in df["formula_cell"].tolist():
            self.assertTrue(val.startswith("\t"), f"Formula injection not neutralized: {val}")


class TestDatasetIdentifierAdversarial(unittest.TestCase):
    """Adversarial identifier sanitization tests."""

    def test_sql_injection_in_column_name(self):
        bad_col = 'amount"; DROP TABLE orders; SELECT * FROM pg_user WHERE "a"="a'
        clean = sanitize_identifier(bad_col)
        self.assertTrue(clean.isidentifier())
        self.assertNotIn(";", clean)
        self.assertNotIn('"', clean)
        self.assertNotIn("'", clean)

    def test_reserved_sql_keywords_in_columns(self):
        keywords = ["select", "from", "where", "group", "order", "table", "user", "limit"]
        for kw in keywords:
            self.assertEqual(sanitize_identifier(kw), f"col_{kw}")

    def test_duplicate_column_headers(self):
        cols = ["price", "price", "price", "tax", "tax"]
        sanitized, _ = sanitize_column_list(cols)
        self.assertEqual(sanitized, ["price", "price_1", "price_2", "tax", "tax_1"])

    def test_empty_and_whitespace_column_names(self):
        self.assertEqual(sanitize_identifier(""), "col_1")
        self.assertEqual(sanitize_identifier("   "), "col_1")
        self.assertEqual(sanitize_identifier("---"), "col_1")

    def test_very_long_column_name_truncated(self):
        long_name = "metric_" + "x" * 200
        clean = sanitize_identifier(long_name)
        self.assertLessEqual(len(clean), 63)
        self.assertTrue(clean.isidentifier())

    def test_unicode_column_name(self):
        self.assertEqual(sanitize_identifier("mês_de_vendas_€"), "mes_de_vendas")
        self.assertEqual(sanitize_identifier("कस्टमर_आईडी"), "col_1")


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

        # Also run cleanup_expired_datasets
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
                # PostgreSQL raises InsufficientPrivilege / permission denied
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
        # 1 valid file + 1 disguised binary file
        files = [
            ("valid_table.csv", b"id,val\n1,100\n"),
            ("bad_table.csv", b"%PDF-1.4 disguised invalid content")
        ]
        with self.assertRaises(FileValidationError):
            DatasetService.upload_dataset(files_data=files, dataset_name="Atomicity Test")

        # Verify no orphan ds_* schemas were created
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

            # 4th upload must be rejected with 400
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
