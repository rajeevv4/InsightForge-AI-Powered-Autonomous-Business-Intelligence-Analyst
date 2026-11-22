"""
Unit tests for the dataset-aware Overview / Analytics pages (Phase 2) and the
async->def conversion of the dataset router.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_workspace_pages
"""

import inspect
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routers import datasets as datasets_router
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import (
    DatasetWorkspaceService,
    WorkspaceCache,
    clamp_limit,
)
from backend.tests.test_dataset_dashboard import SCHEMA, _fake_rows, _profile, _semantic

WS = "backend.app.services.dataset_workspace_service"
DASH = "backend.app.services.dataset_dashboard_service"


class _WorkspaceBase(unittest.TestCase):
    def setUp(self):
        WorkspaceCache.invalidate()
        self.calls = {"profile": 0, "semantic_kwargs": []}

        def _profile_checked(dataset_id, owner_token=None):
            self.calls["profile"] += 1
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()

        def _semantic_spy(dataset_id, owner_token=None, **kwargs):
            self.calls["semantic_kwargs"].append(kwargs)
            return _semantic()

        self.executed = []

        def _exec(sql, schema):
            self.executed.append(sql)
            return _fake_rows(sql)

        patch(f"{WS}.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        patch(f"{WS}.DatasetSemanticService.get_semantic", side_effect=_semantic_spy).start()
        patch(f"{DASH}.DatasetInsightsService.execute_guarded_sql_in_schema", side_effect=_exec).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()


class TestOverview(_WorkspaceBase):

    def test_overview_sections(self):
        r = DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        self.assertEqual(r.section_errors, {})
        self.assertEqual(r.primary_measure, "orders.total_amount")
        self.assertTrue(r.kpis)
        self.assertEqual(len(r.trend.points), 2)
        self.assertIn("city", [b.dimension_column for b in r.breakdowns])  # confirmed N:1 join
        self.assertEqual(r.quality_summary["tables"], 2)
        self.assertFalse(r.cached)

    def test_semantic_model_loaded_without_llm(self):
        DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        self.assertEqual(self.calls["semantic_kwargs"], [{"allow_llm": False}])

    def test_every_query_is_validated_and_schema_scoped(self):
        DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        self.assertTrue(self.executed)
        for sql in self.executed:
            self.assertIn(f'"{SCHEMA}".', sql)
            self.assertIn("LIMIT", sql.upper())

    def test_limit_caps_breakdowns(self):
        r = DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A", limit=1)
        self.assertEqual(len(r.breakdowns), 1)
        self.assertEqual(clamp_limit(99), 8)
        self.assertEqual(clamp_limit(0), 1)

    def test_demo_dataset_rejected(self):
        demo = _profile()
        demo.is_demo, demo.schema_name = True, "insightforge"
        with patch(f"{WS}.DatasetService.get_dataset_profile", return_value=demo):
            with self.assertRaises(FileValidationError) as ctx:
                DatasetWorkspaceService.get_overview("00000000-0000-0000-0000-000000000001", owner_token="tok-A")
        self.assertEqual(ctx.exception.status_code, 400)


class TestCache(_WorkspaceBase):

    def test_second_call_is_cached_for_same_owner(self):
        DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        n_queries = len(self.executed)
        r2 = DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        self.assertTrue(r2.cached)
        self.assertEqual(len(self.executed), n_queries)

    def test_cached_entry_never_served_to_other_token(self):
        DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        with self.assertRaises(FileValidationError) as ctx:
            DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-B")
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(FileValidationError):
            DatasetWorkspaceService.get_overview("ds-dash-1", owner_token=None)

    def test_invalidate_forces_recompute(self):
        DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A")
        WorkspaceCache.invalidate("ds-dash-1")
        self.assertFalse(DatasetWorkspaceService.get_overview("ds-dash-1", owner_token="tok-A").cached)

    def test_params_are_part_of_the_key(self):
        DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", grain="monthly")
        self.assertFalse(DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", grain="weekly").cached)


class TestAnalytics(_WorkspaceBase):

    def test_default_metric_and_grains(self):
        r = DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A")
        self.assertEqual(r.metric, "orders.total_amount")
        self.assertEqual(r.available_grains, ["daily", "weekly", "monthly"])
        self.assertEqual(r.time_column, "order_date")
        keys = [m.key for m in r.metrics]
        self.assertIn("orders.customer_rating", keys)
        self.assertIn("orders.*", keys)

    def test_weekly_grain_uses_week_truncation(self):
        DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", grain="weekly")
        self.assertTrue(any("DATE_TRUNC('WEEK'" in s.upper() for s in self.executed))

    def test_row_count_metric(self):
        r = DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", metric="orders.*")
        self.assertEqual(r.metric, "orders.*")
        self.assertEqual(r.trend.measure_column, "*")

    def test_unknown_metric_and_bad_grain(self):
        with self.assertRaises(FileValidationError) as ctx:
            DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", metric="orders.nope")
        self.assertEqual(ctx.exception.status_code, 400)
        with self.assertRaises(FileValidationError):
            DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A", grain="hourly")

    def test_trend_failure_is_isolated(self):
        def _exec(sql, schema):
            if "date_trunc(" in sql.lower():
                raise RuntimeError("canceling statement due to statement timeout")
            return _fake_rows(sql)
        patch(f"{DASH}.DatasetInsightsService.execute_guarded_sql_in_schema", side_effect=_exec).start()
        r = DatasetWorkspaceService.get_analytics("ds-dash-1", owner_token="tok-A")
        self.assertIsNone(r.trend)
        self.assertIn("statement timeout", r.section_errors["trend"])
        self.assertTrue(r.breakdowns)


class TestEndpoints(_WorkspaceBase):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def test_owner_token_enforced(self):
        for path in ("/api/datasets/ds-dash-1/overview", "/api/datasets/ds-dash-1/analytics"):
            self.assertEqual(self.client.get(path, headers={"X-Owner-Token": "tok-B"}).status_code, 403, path)
            self.assertEqual(self.client.get(path).status_code, 403, path)
            self.assertEqual(self.client.get(path, headers={"X-Owner-Token": "tok-A"}).status_code, 200, path)

    def test_bad_params_400_or_422(self):
        h = {"X-Owner-Token": "tok-A"}
        self.assertEqual(self.client.get("/api/datasets/ds-dash-1/analytics?grain=hourly", headers=h).status_code, 400)
        self.assertEqual(self.client.get("/api/datasets/ds-dash-1/overview?limit=50", headers=h).status_code, 422)


class TestRouterIsSync(unittest.TestCase):
    """The dataset endpoints do blocking DB work; they must be plain `def` (threadpool), not `async def`."""

    def test_no_async_dataset_endpoints(self):
        endpoints = [r.endpoint for r in datasets_router.router.routes]
        self.assertGreaterEqual(len(endpoints), 15)
        async_ones = [e.__name__ for e in endpoints if inspect.iscoroutinefunction(e)]
        self.assertEqual(async_ones, [])


if __name__ == "__main__":
    unittest.main()
