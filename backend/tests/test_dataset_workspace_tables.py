"""
Unit tests for Phase 3: table pages, topic-group pages and live data-quality checks.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_workspace_tables
"""

import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.dataset import ColumnProfile
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import (
    DatasetWorkspaceQuality,
    DatasetWorkspaceTables,
    WorkspaceCache,
    load_context,
    numeric_measure_columns,
)
from backend.tests.test_dataset_dashboard import _col, _fake_rows, _profile, _semantic

WS = "backend.app.services.dataset_workspace_service"
DASH = "backend.app.services.dataset_dashboard_service"


class _Base(unittest.TestCase):
    profile_kwargs = {}

    def setUp(self):
        WorkspaceCache.invalidate()

        def _profile_checked(dataset_id, owner_token=None):
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile(**self.profile_kwargs)

        patch(f"{WS}.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        patch(f"{WS}.DatasetSemanticService.get_semantic", return_value=_semantic()).start()
        self.executed = []

        def _exec(sql, schema):
            self.executed.append(sql)
            return _fake_rows(sql)
        patch(f"{DASH}.DatasetInsightsService.execute_guarded_sql_in_schema", side_effect=_exec).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()


class TestTablePage(_Base):

    def test_table_analysis_shape(self):
        r = DatasetWorkspaceTables.get_table_analysis("ds-dash-1", "tok-A", "orders")
        self.assertEqual(r.table, "orders")
        self.assertEqual(r.primary_measure, "orders.total_amount")
        self.assertEqual([c.name for c in r.columns][:3], ["order_id", "customer_id", "order_date"])
        self.assertTrue(r.kpis)
        self.assertIsNotNone(r.trend)
        self.assertIn("city", [b.dimension_column for b in r.breakdowns])  # safe N:1 join from orders

    def test_dimension_table_counts_rows(self):
        r = DatasetWorkspaceTables.get_table_analysis("ds-dash-1", "tok-A", "customers")
        self.assertEqual(r.primary_measure, "customers.*")
        # customers -> orders is 1:N from this side: no join, so only customers' own columns
        self.assertTrue(all(b.dimension_table == "customers" for b in r.breakdowns or []))

    def test_unknown_table_404(self):
        with self.assertRaises(FileValidationError) as ctx:
            DatasetWorkspaceTables.get_table_analysis("ds-dash-1", "tok-A", "nope")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_column_ranges_only_for_numeric_and_dates(self):
        r = DatasetWorkspaceTables.get_table_analysis("ds-dash-1", "tok-A", "orders")
        by = {c.name: c for c in r.columns}
        self.assertIsNone(by["payment_method"].min_val)  # text values are not echoed


class TestGroupPages(_Base):

    def test_geography_uses_confirmed_n1_join(self):
        r = DatasetWorkspaceTables.get_group_analysis("ds-dash-1", "tok-A", "geography")
        self.assertEqual(r.matched_columns, ["customers.city"])
        city = [b for b in r.breakdowns if b.dimension_column == "city"]
        self.assertEqual(city[0].join_path, "orders.customer_id -> customers.customer_id (N:1)")
        self.assertIn("no numeric geography column", r.section_errors["trend"])

    def test_payments_group(self):
        r = DatasetWorkspaceTables.get_group_analysis("ds-dash-1", "tok-A", "payments")
        self.assertEqual(r.matched_columns, ["orders.payment_method"])
        self.assertEqual([b.dimension_column for b in r.breakdowns], ["payment_method"])

    def test_not_applicable_group_404_and_unknown_400(self):
        with self.assertRaises(FileValidationError) as ctx:
            DatasetWorkspaceTables.get_group_analysis("ds-dash-1", "tok-A", "sellers")
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(FileValidationError) as ctx:
            DatasetWorkspaceTables.get_group_analysis("ds-dash-1", "tok-A", "weather")
        self.assertEqual(ctx.exception.status_code, 400)


class TestGroupUnconfirmed(_Base):
    profile_kwargs = {"confirmed": False}

    def test_geography_skips_unconfirmed_join(self):
        r = DatasetWorkspaceTables.get_group_analysis("ds-dash-1", "tok-A", "geography")
        self.assertEqual(r.breakdowns, [])
        self.assertIn("not confirmed", r.skipped_breakdowns[0].reason)


def _dq_fake(values):
    """Answer the data-quality queries: each AS "alias" gets values.get(alias, default)."""
    def _run(sql, ctx, schema):
        s = sql.lower()
        if "as orphans" in s:
            return [{"orphans": values.get("orphans", 0)}]
        if "as k," in s or 'as "k"' in s:
            return [{"k": "delivered", "n": 900}, {"k": None, "n": 100}]
        if s.startswith("select sum(") and "left join" in s:
            return [{"v": values.get("after", 1000.0)}]
        if s.startswith("select sum("):
            return [{"v": values.get("before", 1000.0)}]
        aliases = re.findall(r'as "?(\w+)"?', sql, flags=re.I)
        row = {}
        for a in aliases:
            if a == "n":
                row[a] = values.get("n", 1000)
            elif a.startswith(("kd", "kn", "c")):
                row[a] = values.get(a, values.get("n", 1000))
            else:
                row[a] = values.get(a, 0)
        return [row]
    return _run


class TestDataQuality(_Base):

    def run_dq(self, values):
        with patch(f"{WS}.DatasetDashboardService._run", side_effect=_dq_fake(values)):
            WorkspaceCache.invalidate()
            return DatasetWorkspaceQuality.get_data_quality("ds-dash-1", "tok-A")

    def test_clean_dataset_passes(self):
        r = self.run_dq({})
        self.assertEqual(r.audit_status, "PASS")
        self.assertTrue(r.primary_key_uniqueness.startswith("PASS"))
        self.assertTrue(r.foreign_key_integrity.startswith("PASS"))
        self.assertTrue(r.join_safety_status.startswith("PASS"))
        self.assertEqual(r.order_status_breakdown, {})  # this profile has no status-like column
        self.assertIsNone(r.status_column)
        kinds = {c.check for c in r.checks}
        self.assertTrue({"primary_key", "foreign_key", "missing_values", "join_safety", "future_dates"} <= kinds)

    def test_dirty_dataset_is_flagged(self):
        # orders is table index 1; key columns: order_id (kd0/kn0); columns c0..; negatives/future dates by index
        r = self.run_dq({"kd0": 990, "kn0": 1000, "orphans": 7, "neg3": 4, "fut2": 2, "c5": 950, "after": 1200.0})
        self.assertEqual(r.audit_status, "FAIL")
        self.assertIn("FAIL", r.primary_key_uniqueness)
        self.assertEqual(r.foreign_key_integrity, "FAIL (7 orphan rows)")
        self.assertIn("4 negative values", r.domain_bounds_status)
        self.assertIn("2 future dates", r.domain_bounds_status)
        self.assertTrue(r.join_safety_status.startswith("FAIL"))
        self.assertEqual(r.missing_value_summary.get("orders.payment_method"), 50)

    def test_status_breakdown_uses_first_status_column(self):
        p = _profile(extra_order_cols=[_col("order_status", distinct=3)])
        with patch(f"{WS}.DatasetService.get_dataset_profile", return_value=p):
            r = self.run_dq({})
        self.assertEqual(r.status_column, "orders.order_status")
        self.assertEqual(r.order_status_breakdown, {"delivered": 900, "(blank)": 100})

    def test_unconfirmed_relationships_skip_fk_and_join(self):
        with patch(f"{WS}.DatasetService.get_dataset_profile", return_value=_profile(confirmed=False)):
            r = self.run_dq({})
        self.assertTrue(r.foreign_key_integrity.startswith("SKIPPED"))
        self.assertTrue(r.join_safety_status.startswith("SKIPPED"))

    def test_key_columns_include_table_named_ids(self):
        p = _profile()
        orders = p.tables[1]
        orders.candidate_pk = None
        self.assertEqual(DatasetWorkspaceQuality.key_columns(orders), ["order_id"])

    def test_fractional_numeric_id_counts_as_measure(self):
        p = _profile(extra_order_cols=[_col("amount", pg_type="NUMERIC(15,2)", role="id", distinct=1000)])
        with patch(f"{WS}.DatasetService.get_dataset_profile", return_value=p):
            wc = load_context("ds-dash-1", "tok-A")
        self.assertIn("amount", numeric_measure_columns(wc, p.tables[1]))
        self.assertNotIn("order_id", numeric_measure_columns(wc, p.tables[1]))


class TestEndpoints(_Base):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def test_owner_token_on_all_phase3_endpoints(self):
        for path in ("/api/datasets/ds-dash-1/tables/orders/analysis",
                     "/api/datasets/ds-dash-1/groups/geography/analysis",
                     "/api/datasets/ds-dash-1/data-quality"):
            self.assertEqual(self.client.get(path, headers={"X-Owner-Token": "tok-B"}).status_code, 403, path)
            self.assertEqual(self.client.get(path).status_code, 403, path)
            self.assertEqual(self.client.get(path, headers={"X-Owner-Token": "tok-A"}).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
