"""
Unit tests for Phase 4: anomaly detection on uploaded datasets.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_dataset_anomalies
"""

import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.anomaly_service import AnomalyService
from backend.app.services.dataset_anomaly_service import (
    GENERIC_EVENT_CATALOG,
    DatasetAnomalyService,
    calibrate_items,
    detect_isolation_forest_generic,
    generic_event_label,
    run_detectors,
    series_is_degenerate,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import WorkspaceCache
from backend.tests.test_dataset_dashboard import _profile, _semantic

WS = "backend.app.services.dataset_workspace_service"
AN = "backend.app.services.dataset_anomaly_service"


def synthetic_daily(n=120, spike_day=80, drop_day=100, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    base = 1000 + 50 * np.sin(np.arange(n) / 7 * 2 * np.pi) + rng.normal(0, 30, n)
    base[spike_day] *= 4.0
    base[drop_day] *= 0.1
    return pd.DataFrame({"period": dates.strftime("%Y-%m-%d"), "period_date": dates, "m0": base,
                         "m1": base / 10 + rng.normal(0, 2, n), "m2": rng.normal(50, 5, n), "row_count": 40.0})


class TestCalibrationEquivalence(unittest.TestCase):
    """The generic pipeline must reproduce the Olist detect_all calibration exactly."""

    def setUp(self):
        self._prev = os.environ.get("USE_FIXTURES")
        os.environ["USE_FIXTURES"] = "1"
        AnomalyService.clear_cache()

    def tearDown(self):
        AnomalyService.clear_cache()
        if self._prev is None:
            os.environ.pop("USE_FIXTURES", None)
        else:
            os.environ["USE_FIXTURES"] = self._prev

    def test_same_severities_as_olist_detect_all(self):
        df = AnomalyService.get_time_series(grain="daily")
        olist = AnomalyService.detect_all(grain="daily", metric="gross_revenue", df=df, iqr_anomalies=[])
        generic, _ = run_detectors(df, "gross_revenue", "daily",
                                   ["gross_revenue", "order_count", "aov", "on_time_delivery_rate"], metric_label="gross_revenue")
        key = lambda a: (a.metric, a.dimension, a.period, a.method, a.severity, a.direction, round(a.deviation_score, 4))
        self.assertTrue(olist.anomalies)
        self.assertEqual(sorted(map(key, olist.anomalies)), sorted(map(key, generic)))

    def test_generic_isolation_forest_matches_olist(self):
        df = AnomalyService.get_time_series(grain="daily")
        feats = ["gross_revenue", "order_count", "aov", "on_time_delivery_rate"]
        a = AnomalyService.detect_isolation_forest(df, confirmed_periods=set())
        b = detect_isolation_forest_generic(df, feats, "gross_revenue", confirmed_periods=set())
        self.assertEqual([(x.period, x.severity, x.deviation_score) for x in a], [(x.period, x.severity, x.deviation_score) for x in b])


class TestDetectionOnSyntheticData(unittest.TestCase):

    def test_spike_and_drop_detected(self):
        df = synthetic_daily()
        items, methods = run_detectors(df, "m0", "daily", ["m0", "m1", "m2"], metric_label="sales.amount")
        self.assertIn("isolation_forest", methods)
        by_period = {}
        for it in items:
            by_period.setdefault(it.period, []).append(it)
        spike, drop = df["period"].iloc[80], df["period"].iloc[100]
        self.assertIn(spike, by_period)
        self.assertIn(drop, by_period)
        self.assertTrue(all(i.direction == "spike" for i in by_period[spike]))
        self.assertTrue(all(i.direction == "drop" for i in by_period[drop]))
        self.assertIn(by_period[spike][0].severity, ("high", "medium"))

    def test_deterministic(self):
        df = synthetic_daily()
        a, _ = run_detectors(df, "m0", "daily", ["m0", "m1", "m2"], metric_label="x")
        b, _ = run_detectors(df, "m0", "daily", ["m0", "m1", "m2"], metric_label="x")
        self.assertEqual([i.model_dump() for i in a], [i.model_dump() for i in b])

    def test_isolation_forest_needs_three_measures(self):
        _, methods = run_detectors(synthetic_daily(), "m0", "daily", ["m0", "m1"], metric_label="x")
        self.assertNotIn("isolation_forest", methods)

    def test_degenerate_series_skipped(self):
        sparse = pd.Series([0] * 80 + [1] * 10 + [3])
        self.assertTrue(series_is_degenerate(sparse))
        self.assertFalse(series_is_degenerate(synthetic_daily()["m0"]))
        df = synthetic_daily()
        df["m0"] = [0.0] * 100 + [1.0] * 19 + [5.0]
        items, methods = run_detectors(df, "m0", "daily", ["m0", "m1", "m2"], metric_label="x")
        self.assertEqual((items, methods), ([], []))

    def test_small_sample_rule_for_ratio_metrics(self):
        df = synthetic_daily()
        df["row_count"] = 5.0  # every day below DEFAULT_MIN_ORDERS
        items, _ = run_detectors(df, "m0", "daily", ["m0"], metric_label="x", ratio_metric=True)
        self.assertEqual([i for i in items if i.method in ("rolling_zscore", "stl_residual")], [])

    def test_calibration_thresholds(self):
        from backend.app.schemas.anomaly import AnomalyItem
        mk = lambda p, m, d: AnomalyItem(metric="x", dimension="overall", period=p, observed=1, expected=1, deviation_score=d,
                                         severity="low", direction="spike", method=m)
        out = {a.period: a.severity for a in calibrate_items([
            mk("a", "rolling_zscore", 8.0), mk("a", "stl_residual", 3.0),   # 2 methods, |dev| 8  -> high
            mk("b", "rolling_zscore", 12.0),                                 # |dev| 12            -> high
            mk("c", "rolling_zscore", 4.0),                                  # |dev| 4             -> medium
            mk("d", "rolling_zscore", 2.6), mk("d", "stl_residual", 2.6),   # 2 methods, |dev|>=2.5 -> medium
            mk("e", "rolling_zscore", 3.0),                                  # single, < 4         -> low
        ])}
        self.assertEqual(out, {"a": "high", "b": "high", "c": "medium", "d": "medium", "e": "low"})


class TestGenericEventCatalog(unittest.TestCase):

    def test_country_neutral_dates(self):
        self.assertEqual(generic_event_label("2024-11-29"), "Black Friday 2024 (candidate)")
        self.assertEqual(generic_event_label("2017-11-24"), "Black Friday 2017 (candidate)")
        self.assertEqual(generic_event_label("2024-12-02"), "Cyber Monday 2024 (candidate)")
        self.assertEqual(generic_event_label("2024-12-25"), "Christmas 2024 (candidate)")
        self.assertEqual(generic_event_label("2024-12-31"), "New Year 2025 (candidate)")
        self.assertIsNone(generic_event_label("2024-10-31"))
        self.assertEqual(generic_event_label("2024-11-25", "weekly"), "Black Friday 2024 (candidate)")

    def test_catalog_is_generic(self):
        names = {e["name"] for e in GENERIC_EVENT_CATALOG}
        self.assertEqual(names, {"New Year", "Black Friday", "Cyber Monday", "Christmas"})
        for e in GENERIC_EVENT_CATALOG:
            self.assertFalse(any(k in e for k in ("revenue", "value", "amount")))  # labels only, no numbers


class _DatasetBase(unittest.TestCase):
    def setUp(self):
        WorkspaceCache.invalidate()

        def _profile_checked(dataset_id, owner_token=None):
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()

        patch(f"{WS}.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        patch(f"{WS}.DatasetSemanticService.get_semantic", return_value=_semantic()).start()
        self.df = synthetic_daily()
        frame_rows = [{"period": r.period, "period_date": r.period, "row_count": 40, "m0": r.m0, "m1": r.m1}
                      for r in self.df.itertuples() if r.Index != 50]  # day 50 missing -> zero-filled

        def _run(sql, ctx, schema):
            s = sql.lower()
            if "date_trunc('day'" in s or "date_trunc('week'" in s:
                return frame_rows
            if "as label" in s:
                return [{"label": f"g{i}", "value": 100.0, "n": 5} for i in range(8)] + [{"label": "big", "value": 5000.0, "n": 5}]
            return []
        patch(f"{AN}.DatasetDashboardService._run", side_effect=_run).start()
        patch("backend.app.services.dataset_dashboard_service.DatasetDashboardService._run", side_effect=_run).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()


class TestDatasetAnomalies(_DatasetBase):

    def test_response_shape_and_zero_fill(self):
        r = DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A")
        self.assertEqual(r.metric, "orders.total_amount")
        self.assertEqual(len(r.time_series), len(self.df))  # missing day re-inserted
        missing = self.df["period"].iloc[50]
        self.assertEqual(next(p.observed for p in r.time_series if p.period == missing), 0.0)  # SUM -> zero-filled
        self.assertIn("rolling_zscore", r.methods_run)
        self.assertTrue(any(s.dimension.endswith(":big") for s in r.slice_outliers))
        self.assertTrue(all(s.period == "All time" for s in r.slice_outliers))  # no Olist "2017-2018" label

    def test_severity_filter_is_a_subset_with_same_severities(self):
        full = DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A")
        for sev in ("high", "medium", "low"):
            sub = DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A", severity=sev)
            self.assertEqual(sub.total_anomalies, sum(1 for a in full.anomalies if a.severity == sev))
            self.assertTrue(all(a.severity == sev for a in sub.anomalies))

    def test_bad_params(self):
        for kwargs in ({"grain": "hourly"}, {"severity": "critical"}, {"metric": "orders.nope"}):
            with self.assertRaises(FileValidationError) as ctx:
                DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A", **kwargs)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_cache_key_includes_dataset_and_owner(self):
        DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A")
        self.assertTrue(DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-A").cached)
        with self.assertRaises(FileValidationError):
            DatasetAnomalyService.get_anomalies("ds-dash-1", "tok-B")

    def test_quick_insights_items_have_rendered_fields(self):
        items = DatasetAnomalyService.quick_insights_items("ds-dash-1", "tok-A")
        self.assertTrue(items)
        self.assertEqual(set(items[0]), {"period", "metric", "actual_value", "expected_value", "deviation_pct", "severity", "label", "direction"})

    def test_scan_covers_time_based_measures(self):
        r = DatasetAnomalyService.scan("ds-dash-1", "tok-A")
        self.assertIn("orders.total_amount", r.scanned_metrics)
        self.assertNotIn("customers.*", r.scanned_metrics)  # customers has no time column in this profile
        self.assertEqual(r.high_severity_count, sum(1 for a in r.anomalies if a.severity == "high"))


class TestAnomalyEndpoints(_DatasetBase):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def test_owner_token_enforced(self):
        for method, path in (("get", "/api/datasets/ds-dash-1/anomalies"), ("post", "/api/datasets/ds-dash-1/anomalies/scan")):
            call = getattr(self.client, method)
            self.assertEqual(call(path, headers={"X-Owner-Token": "tok-B"}).status_code, 403, path)
            self.assertEqual(call(path).status_code, 403, path)
            self.assertEqual(call(path, headers={"X-Owner-Token": "tok-A"}).status_code, 200, path)

    def test_scan_is_rate_limited_like_olist(self):
        from backend.app.routers import datasets as r
        src = open(r.__file__).read()
        self.assertIn('@limiter.limit("10/minute")\ndef scan_dataset_anomalies(', src)


if __name__ == "__main__":
    unittest.main()
