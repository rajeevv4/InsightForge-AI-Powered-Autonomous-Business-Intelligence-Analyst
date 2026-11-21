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
from backend.app.limiter import get_client_ip
from backend.app.services.dataset_file_parser import DatasetFileParser, FileValidationError, infer_column_type
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

    def test_signed_numbers_stay_numeric_and_sum(self):
        """Signed numeric values like (-5.5, 10, -2, +3) remain NUMERIC and sum correctly."""
        p = self.dir_path / "signed_numbers.csv"
        p.write_text("id,amount\n1,-5.5\n2,10\n3,-2\n4,+3\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "signed_numbers.csv")
        self.assertEqual(cols[1], "amount")
        # Check inferred column type
        vals = df["amount"].dropna().astype(str).tolist()
        col_type, _ = infer_column_type(vals)
        self.assertEqual(col_type, "NUMERIC(15, 2)")
        # Sum numeric values
        total = df["amount"].astype(float).sum()
        self.assertAlmostEqual(total, 5.5, places=2)

    def test_text_column_preserves_dash_and_plus_plan(self):
        """Text columns with '-' and '+1 plan' keep equality and grouping semantics without tabs."""
        p = self.dir_path / "plans.csv"
        p.write_text("plan,code\n+1 plan,-\n+1 plan,-\n", encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "plans.csv")
        self.assertEqual(df["plan"].iloc[0], "+1 plan")
        self.assertEqual(df["code"].iloc[0], "-")
        self.assertFalse(df["plan"].iloc[0].startswith("\t"))
        self.assertFalse(df["code"].iloc[0].startswith("\t"))
        self.assertEqual(len(df["plan"].unique()), 1)

    def test_hyperlink_formula_neutralized_and_flagged(self):
        """Formula injection like =HYPERLINK(...) is prefixed with tab and flagged in warnings."""
        p = self.dir_path / "hyperlink_test.csv"
        p.write_text('name,link\nAlice,"=HYPERLINK(""http://evil.com"",""click"")"\n', encoding="utf-8")
        df, tbl, cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(p, "hyperlink_test.csv")
        self.assertTrue(df["link"].iloc[0].startswith("\t="))
        warn_cols = [w["column"] for w in warnings if "Formula injection" in w.get("warning", "")]
        self.assertIn("link", warn_cols)


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


class TestProxyAndAbuseCaps(unittest.TestCase):
    """Tests for trusted reverse proxy IP extraction and dataset abuse caps."""

    def test_trusted_proxy_ip_extraction(self):
        """X-Forwarded-For is respected only when TRUSTED_PROXIES_ENABLED is True."""
        mock_req = MagicMock()
        mock_req.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
        mock_req.client = MagicMock(host="10.0.0.1")

        with patch.object(settings, "TRUSTED_PROXIES_ENABLED", False):
            ip = get_client_ip(mock_req)
            self.assertEqual(ip, "10.0.0.1")

        with patch.object(settings, "TRUSTED_PROXIES_ENABLED", True):
            ip = get_client_ip(mock_req)
            self.assertEqual(ip, "203.0.113.195")

    def test_global_dataset_cap_rejected(self):
        """Upload rejected with 507 when active global datasets reach MAX_GLOBAL_DATASETS."""
        with patch.object(DatasetService, "_assert_live_db"):
            with patch.object(DatasetService, "check_database_storage_capacity"):
                with patch.object(DatasetService, "count_global_datasets", return_value=settings.MAX_GLOBAL_DATASETS):
                    with self.assertRaises(FileValidationError) as ctx:
                        DatasetService.upload_dataset([("sample.csv", b"a,b\n1,2\n")])
                    self.assertEqual(ctx.exception.status_code, 507)
                    self.assertIn("Global dataset limit reached", str(ctx.exception))

    def test_daily_ip_cap_rejected(self):
        """Upload rejected with 429 when client IP exceeds MAX_DATASETS_PER_IP_PER_DAY."""
        with patch.object(DatasetService, "_assert_live_db"):
            with patch.object(DatasetService, "check_database_storage_capacity"):
                with patch.object(DatasetService, "count_global_datasets", return_value=0):
                    with patch.object(DatasetService, "count_daily_ip_uploads", return_value=settings.MAX_DATASETS_PER_IP_PER_DAY):
                        with self.assertRaises(FileValidationError) as ctx:
                            DatasetService.upload_dataset([("sample.csv", b"a,b\n1,2\n")], client_ip="203.0.113.50")
                        self.assertEqual(ctx.exception.status_code, 429)
                        self.assertIn("Daily upload limit", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
