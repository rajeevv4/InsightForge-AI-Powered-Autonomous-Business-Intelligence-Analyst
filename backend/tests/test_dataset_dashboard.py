"""
Unit tests for the uploaded-dataset Dashboard (GET /api/datasets/{id}/dashboard).
Hermetic: profile, semantic model and query execution are mocked; the real SQLValidator
is used wherever SQL text matters.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_dashboard
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.dataset import ColumnProfile, DatasetProfile, RelationshipProfile, TableProfile
from backend.app.schemas.dataset_semantic import (
    DatasetSemanticResponse,
    DimensionDefinition,
    MeasureDefinition,
    SemanticModel,
    TimeColumnDefinition,
)
from backend.app.services.dataset_dashboard_service import DatasetDashboardService, quote_ident
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.sql_validator import DatasetSQLContext

SCHEMA = "ds_0a1b2c3d"
MOD = "backend.app.services.dataset_dashboard_service"


def _col(name, pg_type="TEXT", role="dimension", distinct=5, null_pct=0.0):
    return ColumnProfile(original_name=name, safe_name=name, pg_type=pg_type, role=role,
                         distinct_count=distinct, null_pct=null_pct)


def _profile(confirmed=True, customer_key_unique=True, extra_order_cols=None, rel_direction="n1") -> DatasetProfile:
    customers = TableProfile(
        id="t-c", original_name="customers.csv", safe_name="customers", row_count=100, column_count=3,
        candidate_pk="customer_id", candidate_time_column=None, quality_findings=[],
        columns=[
            _col("customer_id", role="id", distinct=100 if customer_key_unique else 60),
            _col("city", distinct=8),
            _col("customer_name", distinct=100),  # unique -> not a sensible grouping
        ],
    )
    orders = TableProfile(
        id="t-o", original_name="orders.csv", safe_name="orders", row_count=1000, column_count=6,
        candidate_pk="order_id", candidate_time_column="order_date",
        quality_findings=[{"type": "high_null_column", "column": "notes", "severity": "medium", "message": "notes is 60% empty"},
                          {"column": "order_date", "warning": "Ambiguous date format"}],  # legacy shape
        columns=[
            _col("order_id", role="id", distinct=1000),
            _col("customer_id", role="id", distinct=100),
            _col("order_date", pg_type="TIMESTAMP", role="datetime", distinct=300),
            _col("total_amount", pg_type="NUMERIC(12,2)", role="measure", distinct=900),
            _col("customer_rating", pg_type="INTEGER", role="measure", distinct=5),
            _col("payment_method", distinct=4),
        ] + (extra_order_cols or []),
    )
    if rel_direction == "n1":  # orders (many) -> customers (one): safe
        rel = RelationshipProfile(parent_table="customers", parent_column="customer_id", child_table="orders",
                                  child_column="customer_id", cardinality="1:N", confidence=0.95, confirmed=confirmed)
    else:  # customers is the child: fact(orders)->customers would be 1:N
        rel = RelationshipProfile(parent_table="orders", parent_column="customer_id", child_table="customers",
                                  child_column="customer_id", cardinality="1:N", confidence=0.95, confirmed=confirmed)
    return DatasetProfile(
        id="ds-dash-1", name="Shop", schema_name=SCHEMA, status="ready", share_samples=False,
        source_files=["customers.csv", "orders.csv"], size_bytes=1, created_at=datetime.now(timezone.utc),
        expires_at=None, is_demo=False, tables=[customers, orders], relationships=[rel],
    )


def _measure(table, column, agg, name=None):
    return MeasureDefinition(name=name or (column or f"{table} rows"), safe_name=f"{table}_{column or 'count'}",
                             table=table, column=column, aggregation=agg)


def _dim(table, column):
    return DimensionDefinition(name=column.replace("_", " ").title(), safe_name=f"{table}_{column}", table=table,
                               column=column, data_type="TEXT")


def _semantic(measures=None, dims=None) -> DatasetSemanticResponse:
    model = SemanticModel(
        dataset_id="ds-dash-1", dataset_name="Shop",
        measures=measures if measures is not None else [
            _measure("customers", None, "COUNT"), _measure("orders", None, "COUNT"),
            _measure("orders", "customer_rating", "AVG", "Customer Rating"),
            _measure("orders", "total_amount", "SUM", "Total Amount"),
        ],
        dimensions=dims if dims is not None else [
            _dim("orders", "payment_method"), _dim("customers", "city"), _dim("customers", "customer_name"),
            _dim("orders", "order_id"),
        ],
        time_columns=[TimeColumnDefinition(name="Order Date", safe_name="order_date", table="orders",
                                           column="order_date", data_type="TIMESTAMP")],
    )
    now = datetime.now(timezone.utc)
    return DatasetSemanticResponse(dataset_id="ds-dash-1", status="draft", semantic_model=model,
                                   starter_questions=[], created_at=now, updated_at=now)


def _fake_rows(sql: str):
    """Canned query results keyed on the shape of the generated SQL."""
    s = sql.lower()
    if "date_trunc('day'" in s:
        return [{"period": f"2024-01-{d:02d}", "period_date": f"2024-01-{d:02d}", "metric_val": 100.0} for d in range(1, 11)]
    if "date_trunc('month'" in s:
        return [{"period": "2024-01-01", "value": 600.0}, {"period": "2024-02-01", "value": 400.0}]
    if "as label" in s:
        # 12 groups incl. a NULL group -> top 10 + "other" rollup
        rows = [{"label": f"g{i}", "value": float(100 - i), "n": 10} for i in range(11)]
        rows.append({"label": None, "value": 5.0, "n": 1})
        return rows
    if "count(*)" in s:
        return [{"k0": 1000, "k1": 3.9, "k2": 1000.0}] if '"orders"' in s else [{"k0": 100}]
    return []


class _Base(unittest.TestCase):
    def setUp(self):
        self.p_profile = patch(f"{MOD}.DatasetService.get_dataset_profile")
        self.p_sem = patch(f"{MOD}.DatasetSemanticService.get_semantic")
        self.p_exec = patch(f"{MOD}.DatasetInsightsService.execute_guarded_sql_in_schema")
        self.mock_profile = self.p_profile.start()
        self.mock_sem = self.p_sem.start()
        self.mock_exec = self.p_exec.start()
        self.mock_profile.return_value = _profile()
        self.mock_sem.return_value = _semantic()
        self.executed = []

        def _exec(sanitized_sql, schema_name):
            self.executed.append(sanitized_sql)
            return _fake_rows(sanitized_sql)
        self.mock_exec.side_effect = _exec

    def tearDown(self):
        patch.stopall()


class TestDashboardPayload(_Base):

    def test_payload_shape_all_sections(self):
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        d = r.model_dump()
        for key in ("dataset_id", "dataset_name", "primary_measure", "kpis", "trend", "breakdowns",
                    "skipped_breakdowns", "data_quality", "anomalies", "section_errors"):
            self.assertIn(key, d)
        self.assertEqual(r.primary_measure, "orders.total_amount")
        self.assertEqual(r.section_errors, {})
        labels = {(k.table, k.column, k.aggregation): k.value for k in r.kpis}
        self.assertEqual(labels[("customers", None, "COUNT")], 100)
        self.assertEqual(labels[("orders", "total_amount", "SUM")], 1000.0)
        self.assertEqual(labels[("orders", "customer_rating", "AVG")], 3.9)
        self.assertEqual([p["value"] for p in r.trend.points], [600.0, 400.0])
        self.assertEqual(len(r.data_quality), 2)
        legacy = [f for f in r.data_quality[1].findings if f["column"] == "order_date"][0]
        self.assertEqual(legacy["message"], "Ambiguous date format")  # legacy {"warning"} shape normalized
        self.assertIsNotNone(r.anomalies)
        self.assertIn("30 days", r.anomalies.note)  # only 10 daily points in the fake data

    def test_every_query_is_validated_schema_qualified_and_quoted(self):
        DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertTrue(self.executed)
        for sql in self.executed:
            self.assertIn(f'"{SCHEMA}".', sql)
            self.assertIn("LIMIT", sql.upper())  # added by SQLValidator -> proves validation ran

    def test_breakdown_other_rollup_sums_to_total(self):
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        b = r.breakdowns[0]
        self.assertEqual(len(b.items), 10)
        self.assertEqual(b.other_groups, 2)
        shown = sum(i.value for i in b.items)
        self.assertAlmostEqual(shown + b.other_value, b.total_value)
        self.assertAlmostEqual(b.total_value, sum(100 - i for i in range(11)) + 5.0)


class TestJoinSafety(_Base):

    def test_confirmed_n1_join_is_used_with_left_join(self):
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        city = [b for b in r.breakdowns if b.dimension_column == "city"]
        self.assertEqual(len(city), 1)
        self.assertEqual(city[0].join_path, "orders.customer_id -> customers.customer_id (N:1)")
        join_sql = [s for s in self.executed if '"customers" AS "d"' in s]
        self.assertTrue(join_sql and "LEFT JOIN" in join_sql[0])

    def test_1_to_n_path_is_skipped(self):
        self.mock_profile.return_value = _profile(rel_direction="1n")
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertNotIn("city", [b.dimension_column for b in r.breakdowns])
        skipped = {s.dimension: s.reason for s in r.skipped_breakdowns}
        self.assertIn("would multiply rows", skipped["customers.city"])
        self.assertFalse(any('"customers" AS "d"' in s for s in self.executed))

    def test_unconfirmed_relationship_is_skipped(self):
        self.mock_profile.return_value = _profile(confirmed=False)
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertIn("not confirmed", {s.dimension: s.reason for s in r.skipped_breakdowns}["customers.city"])

    def test_non_unique_dimension_key_is_skipped(self):
        self.mock_profile.return_value = _profile(customer_key_unique=False)
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertIn("not unique", {s.dimension: s.reason for s in r.skipped_breakdowns}["customers.city"])

    def test_identifier_and_unique_columns_are_not_breakdowns(self):
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        cols = [b.dimension_column for b in r.breakdowns]
        self.assertNotIn("order_id", cols)
        self.assertNotIn("customer_name", cols)


class TestSectionIsolation(_Base):

    def test_failing_trend_does_not_break_other_sections(self):
        def _exec(sanitized_sql, schema_name):
            if "date_trunc('month'" in sanitized_sql.lower():
                raise RuntimeError("canceling statement due to statement timeout")
            return _fake_rows(sanitized_sql)
        self.mock_exec.side_effect = _exec
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertIsNone(r.trend)
        self.assertIn("statement timeout", r.section_errors["trend"])
        self.assertTrue(r.kpis)
        self.assertTrue(r.breakdowns)
        self.assertIsNotNone(r.data_quality)
        self.assertIsNotNone(r.anomalies)

    def test_semantic_failure_keeps_data_quality(self):
        self.mock_sem.side_effect = RuntimeError("boom")
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertIsNotNone(r.data_quality)
        self.assertIsNone(r.kpis)
        self.assertIn("semantic model unavailable", r.section_errors["kpis"])

    def test_no_time_column_gives_reason(self):
        sem = _semantic()
        sem.semantic_model.time_columns = []
        self.mock_sem.return_value = sem
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertIsNone(r.trend)
        self.assertIn("no date/time column", r.section_errors["trend"])


class TestIdentifierSafety(_Base):

    def test_quote_ident_escapes_quotes_and_spaces(self):
        self.assertEqual(quote_ident("amount"), '"amount"')
        self.assertEqual(quote_ident("with space"), '"with space"')
        self.assertEqual(quote_ident('odd "col"'), '"odd ""col"""')
        self.assertEqual(quote_ident('x"; DROP TABLE t; --'), '"x""; DROP TABLE t; --"')

    def test_weird_column_name_is_quoted_in_generated_sql(self):
        weird = 'net "amount" total'
        self.mock_profile.return_value = _profile(extra_order_cols=[_col(weird, pg_type="NUMERIC(10,2)", role="measure", distinct=50)])
        self.mock_sem.return_value = _semantic(measures=[_measure("orders", weird, "SUM", "Net Amount")], dims=[])
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        self.assertEqual(r.primary_measure, f"orders.{weird}")
        self.assertTrue(any('SUM("net ""amount"" total")' in s for s in self.executed), self.executed)

    def test_tampered_semantic_measures_are_rejected(self):
        """Users can PATCH the semantic model; aggregation/column must be re-checked."""
        self.mock_sem.return_value = _semantic(measures=[
            _measure("orders", "total_amount", "SUM); DROP TABLE orders; --"),
            _measure("orders", "no_such_column", "SUM"),
            _measure("orders", "payment_method", "SUM"),   # TEXT column
            _measure("ds_other.secret", "x", "SUM"),        # unknown table
            _measure("orders", "total_amount", "SUM", "Total Amount"),
        ], dims=[])
        r = DatasetDashboardService.get_dashboard("ds-dash-1", owner_token="tok")
        kpi_cols = [(k.column, k.aggregation) for k in r.kpis if k.column]
        self.assertEqual(kpi_cols, [("total_amount", "SUM")])
        for sql in self.executed:
            self.assertNotIn("DROP", sql.upper())
            self.assertNotIn("ds_other", sql)


class TestDashboardEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

        def _profile_with_owner_check(dataset_id, owner_token=None):
            if owner_token != "right-token":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()
        patch(f"{MOD}.DatasetService.get_dataset_profile", side_effect=_profile_with_owner_check).start()
        patch(f"{MOD}.DatasetSemanticService.get_semantic", return_value=_semantic()).start()
        patch(f"{MOD}.DatasetInsightsService.execute_guarded_sql_in_schema",
              side_effect=lambda sql, schema: _fake_rows(sql)).start()

    def tearDown(self):
        patch.stopall()

    def test_wrong_token_returns_403_with_detail(self):
        res = self.client.get("/api/datasets/ds-dash-1/dashboard", headers={"X-Owner-Token": "wrong"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Access denied", res.json()["detail"])

    def test_missing_token_returns_403(self):
        res = self.client.get("/api/datasets/ds-dash-1/dashboard")
        self.assertEqual(res.status_code, 403)

    def test_right_token_returns_200(self):
        res = self.client.get("/api/datasets/ds-dash-1/dashboard", headers={"X-Owner-Token": "right-token"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["primary_measure"], "orders.total_amount")

    def test_demo_dataset_is_not_applicable(self):
        demo = _profile()
        demo.is_demo = True
        demo.schema_name = "insightforge"
        with patch(f"{MOD}.DatasetService.get_dataset_profile", return_value=demo):
            res = self.client.get("/api/datasets/00000000-0000-0000-0000-000000000001/dashboard",
                                  headers={"X-Owner-Token": "right-token"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("only available for uploaded datasets", res.json()["detail"])


class TestPlannerUnits(unittest.TestCase):

    def test_find_safe_join_directions(self):
        p = _profile()
        rel, reason = DatasetDashboardService.find_safe_join(p, "orders", "customers")
        self.assertIsNotNone(rel)
        self.assertIsNone(reason)
        rel, reason = DatasetDashboardService.find_safe_join(p, "customers", "orders")
        self.assertIsNone(rel)
        self.assertIn("would multiply rows", reason)

    def test_validator_context_rejects_other_schema(self):
        ctx = DatasetSQLContext(schema_name=SCHEMA, allowed_tables={"orders"}, relationships=[],
                                table_columns={"orders": {"total_amount"}}, is_demo=False)
        with self.assertRaises(ValueError):
            DatasetDashboardService._run('SELECT COUNT(*) FROM "ds_ffffffff"."orders"', ctx, SCHEMA)


if __name__ == "__main__":
    unittest.main()
