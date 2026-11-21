import io
import os
import tempfile
import unittest
from pathlib import Path
import pandas as pd

from backend.app.services.dataset_sanitizer import (
    sanitize_identifier,
    sanitize_column_list,
    sanitize_table_name,
)
from backend.app.services.dataset_file_parser import (
    DatasetFileParser,
    FileValidationError,
    check_date_ambiguity,
    infer_column_type,
)
from backend.app.services.dataset_profiler import DatasetProfiler


class TestDatasetSanitizer(unittest.TestCase):
    """Unit tests for identifier sanitization and SQL injection neutralization."""

    def test_sql_injection_identifiers(self):
        injections = [
            ('a"; DROP TABLE x;--', 'a_drop_table_x'),
            ("admin' OR '1'='1", "admin_or_1_1"),
            ("1; SELECT * FROM pg_shadow;--", "col_1_select_from_pg_shadow"),
            ("table -- comment", "table_comment"),
        ]
        for bad_id, expected in injections:
            res = sanitize_identifier(bad_id)
            self.assertEqual(res, expected)
            self.assertTrue(res.isidentifier() or res.startswith("col_"))
            self.assertNotIn(";", res)
            self.assertNotIn('"', res)
            self.assertNotIn("'", res)

    def test_reserved_sql_keywords(self):
        keywords = ["select", "order", "group", "table", "user", "where", "from", "limit"]
        for kw in keywords:
            res = sanitize_identifier(kw)
            self.assertEqual(res, f"col_{kw}")

    def test_emoji_and_special_characters(self):
        self.assertEqual(sanitize_identifier("sales_📊_2023"), "sales_2023")
        self.assertEqual(sanitize_identifier("Customer-Name (Main & Secondary)"), "customer_name_main_secondary")
        self.assertEqual(sanitize_identifier("prix_en_€"), "prix_en")
        self.assertEqual(sanitize_identifier(""), "col_1")
        self.assertEqual(sanitize_identifier("---"), "col_1")

    def test_leading_digit_prefixing(self):
        self.assertEqual(sanitize_identifier("123_revenue"), "col_123_revenue")
        self.assertEqual(sanitize_identifier("2024_forecast"), "col_2024_forecast")

    def test_deduplicate_column_names(self):
        cols = ["category", "category", "category", "amount", "amount"]
        sanitized, mapping = sanitize_column_list(cols)
        self.assertEqual(sanitized, ["category", "category_1", "category_2", "amount", "amount_1"])

    def test_length_truncation(self):
        long_name = "a" * 120
        sanitized = sanitize_identifier(long_name)
        self.assertLessEqual(len(sanitized), 63)
        self.assertEqual(len(sanitized), 63)

    def test_table_name_path_traversal(self):
        bad_filenames = [
            ("../../etc/passwd.csv", "passwd"),
            (r"..\..\..\boot.ini", "boot"),
            ("/var/log/syslog.tsv", "syslog"),
            ("my-awesome-sales-2023!.xlsx", "my_awesome_sales_2023"),
        ]
        for fname, expected in bad_filenames:
            res = sanitize_table_name(fname)
            self.assertEqual(res, expected)


class TestDatasetFileParser(unittest.TestCase):
    """Unit tests for file parsing, format safety, encoding detection, and bound enforcement."""

    def test_empty_file_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"")
            tmp_path = Path(f.name)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.validate_file_content(tmp_path, "empty.csv")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("empty", ctx.exception.message.lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_header_only_file_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"id,name,amount\n")
            tmp_path = Path(f.name)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.parse_to_dataframe(tmp_path, "header_only.csv")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("no data rows", ctx.exception.message.lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_disguised_binary_file_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x3e\x00" * 20)
            tmp_path = Path(f.name)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.validate_file_content(tmp_path, "binary_virus.csv")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("binary", ctx.exception.message.lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_macro_excel_rejected(self):
        with tempfile.NamedTemporaryFile(suffix=".xlsm", delete=False) as f:
            f.write(b"dummy")
            tmp_path = Path(f.name)

        try:
            with self.assertRaises(FileValidationError) as ctx:
                DatasetFileParser.validate_file_content(tmp_path, "dangerous.xlsm")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("macro", ctx.exception.message.lower())
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_utf8_bom_and_semicolon_parsing(self):
        content = "\ufeffid;nom;salaire\n1;Alice;5000\n2;Bob;6200\n".encode("utf-8")
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            df, table_name, safe_cols, mapping, warnings = DatasetFileParser.parse_to_dataframe(tmp_path, "french_salaries.csv")
            self.assertEqual(len(df), 2)
            self.assertEqual(list(df.columns), ["id", "nom", "salaire"])
            self.assertEqual(table_name, "french_salaries")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_ambiguous_date_detection(self):
        # Dates like 05/06/2023 can be May 6 or June 5
        dates = ["05/06/2023", "07/08/2023", "01/02/2023"]
        is_amb, sample = check_date_ambiguity(dates)
        self.assertTrue(is_amb)
        self.assertEqual(sample, "05/06/2023")

        pg_type, warning = infer_column_type(dates)
        self.assertEqual(pg_type, "DATE")
        self.assertIsNotNone(warning)
        self.assertIn("ambiguous", warning.lower())


class TestDatasetProfiler(unittest.TestCase):
    """Unit tests for deterministic profiling, privacy enforcement, and relationship detection."""

    def setUp(self):
        self.df_customers = pd.DataFrame({
            "customer_id": [f"C_{i}" for i in range(1, 11)],
            "name": [f"Customer {i}" for i in range(1, 11)],
            "signup_date": pd.date_range("2023-01-01", periods=10, freq="D"),
            "status": ["active"] * 10,  # Constant column
            "notes": [None] * 8 + ["note 1", "note 2"]  # 80% null
        })

        self.df_orders = pd.DataFrame({
            "order_id": [f"O_{i}" for i in range(1, 21)],
            "customer_id": [f"C_{(i % 10) + 1}" for i in range(1, 21)],
            "amount": [19.99 * i for i in range(1, 21)],
            "refund_amount": [-10.0 if i == 5 else 0.0 for i in range(1, 21)]  # Suspicious negative
        })

    def test_sample_values_privacy_flag(self):
        col_map = {c: c for c in self.df_customers.columns}
        # share_samples=False -> top_5 should be empty
        cust_profile_private = DatasetProfiler.profile_dataframe(
            df=self.df_customers,
            original_table_name="customers",
            safe_table_name="customers",
            column_mapping=col_map,
            share_samples=False
        )
        for col in cust_profile_private.columns:
            self.assertFalse(col.stats.get("top_5"))

        # share_samples=True -> top_5 should contain values
        cust_profile_shared = DatasetProfiler.profile_dataframe(
            df=self.df_customers,
            original_table_name="customers",
            safe_table_name="customers",
            column_mapping=col_map,
            share_samples=True
        )
        for col in cust_profile_shared.columns:
            if col.safe_name == "name":
                self.assertGreater(len(col.stats.get("top_5", [])), 0)

    def test_deterministic_quality_findings(self):
        col_map_cust = {c: c for c in self.df_customers.columns}
        cust_profile = DatasetProfiler.profile_dataframe(
            df=self.df_customers,
            original_table_name="customers",
            safe_table_name="customers",
            column_mapping=col_map_cust,
            share_samples=False
        )
        finding_types = [f["type"] for f in cust_profile.quality_findings]
        self.assertIn("constant_column", finding_types)
        self.assertIn("high_null_column", finding_types)

        col_map_ord = {c: c for c in self.df_orders.columns}
        orders_profile = DatasetProfiler.profile_dataframe(
            df=self.df_orders,
            original_table_name="orders",
            safe_table_name="orders",
            column_mapping=col_map_ord,
            share_samples=False
        )
        order_finding_types = [f["type"] for f in orders_profile.quality_findings]
        self.assertIn("suspicious_negative_values", order_finding_types)

    def test_relationship_inference(self):
        col_map_cust = {c: c for c in self.df_customers.columns}
        cust_profile = DatasetProfiler.profile_dataframe(
            df=self.df_customers,
            original_table_name="customers",
            safe_table_name="customers",
            column_mapping=col_map_cust,
            share_samples=False
        )

        col_map_ord = {c: c for c in self.df_orders.columns}
        orders_profile = DatasetProfiler.profile_dataframe(
            df=self.df_orders,
            original_table_name="orders",
            safe_table_name="orders",
            column_mapping=col_map_ord,
            share_samples=False
        )

        tables_dict = {
            "customers": self.df_customers,
            "orders": self.df_orders
        }
        profiles_dict = {
            "customers": cust_profile,
            "orders": orders_profile
        }
        relationships = DatasetProfiler.infer_relationships(tables_dict, profiles_dict)
        self.assertGreater(len(relationships), 0)

        rel = relationships[0]
        self.assertEqual(rel.parent_table, "customers")
        self.assertEqual(rel.parent_column, "customer_id")
        self.assertEqual(rel.child_table, "orders")
        self.assertEqual(rel.child_column, "customer_id")
        self.assertEqual(rel.cardinality, "1:N")
        self.assertGreaterEqual(rel.confidence, 0.85)


if __name__ == "__main__":
    unittest.main()
