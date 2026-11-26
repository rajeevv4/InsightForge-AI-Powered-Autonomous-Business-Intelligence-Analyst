"""
Unit tests for the baseline forecast (Olist + uploaded datasets).

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_forecast
"""

import inspect
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.anomaly import AnomalyItem
from backend.app.schemas.forecast import ForecastResponse
from backend.app.services import forecast_service as fs
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import WorkspaceCache
from backend.app.services.forecast_service import (
    FORECAST_RULES,
    DatasetForecastService,
    OlistForecastService,
    anomaly_deltas,
    clamp_horizon,
    run_forecast,
    trim_monthly,
)
from backend.tests.test_dataset_dashboard import _profile, _semantic

WS = "backend.app.services.dataset_workspace_service"
MONTHS = pd.date_range("2021-01-01", periods=30, freq="MS")


def _resp(h=3, exclude=False):
    return ForecastResponse(dataset_id="x", dataset_name="x", horizon=h, status="refused", exclude_anomalies=exclude)


def trend_series(n=30, seed=0):
    return pd.Series(1000 + 40 * np.arange(n) + np.random.default_rng(seed).normal(0, 15, n), index=MONTHS[:n])


def noise_series(seed=3, n=24):
    return pd.Series(np.clip(np.random.default_rng(seed).normal(100, 70, n), 0, None), index=MONTHS[:n])


def _assert_bands(tc, points):
    for p in points:
        tc.assertGreaterEqual(p.lower_95, 0.0)
        tc.assertLessEqual(p.lower_95, p.lower_80)
        tc.assertLessEqual(p.lower_80, p.expected)
        tc.assertLessEqual(p.expected, p.upper_80)
        tc.assertLessEqual(p.upper_80, p.upper_95)


class TestForecastCore(unittest.TestCase):

    def test_clear_trend_is_good(self):
        r = run_forecast(_resp(), trend_series(), None, 3, {})
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.reliability, "Good")
        self.assertEqual(r.model_kind, "monthly")
        self.assertEqual(len(r.forecast), 3)
        self.assertEqual(r.forecast[0].period, "2023-07")
        self.assertTrue(r.backtest.beats_naive)
        self.assertLess(r.backtest.mape, r.backtest.naive_mape)
        _assert_bands(self, r.forecast)

    def test_pure_noise_is_refused_without_numbers(self):
        refused = 0
        for seed in range(10):
            r = run_forecast(_resp(), noise_series(seed), None, 3, {})
            if r.status == "refused":
                refused += 1
                self.assertEqual(r.forecast, [])
                self.assertIsNone(r.reliability)
                self.assertTrue(r.reason)
        self.assertGreaterEqual(refused, 9)  # 1 in 10 white-noise series may look forecastable by chance

    def test_short_series_is_refused(self):
        r = run_forecast(_resp(), trend_series(6), None, 3, {})
        self.assertEqual(r.status, "refused")
        self.assertIn("12 clean months", r.reason)
        # 6 months but only 60 days of daily data -> still refused
        days = pd.date_range("2021-05-03", periods=60, freq="D")
        r = run_forecast(_resp(), trend_series(6), None, 3, {}, lambda: pd.Series(100.0, index=days))
        self.assertEqual(r.status, "refused")

    def test_daily_model_when_fewer_than_12_months(self):
        days = pd.date_range("2024-01-01", "2024-06-30", freq="D")
        rng = np.random.default_rng(1)
        daily = pd.Series(200 + 0.5 * np.arange(len(days)) + 30 * np.sin(np.arange(len(days)) * 2 * np.pi / 7)
                          + rng.normal(0, 10, len(days)), index=days)
        monthly = daily.groupby(daily.index.to_period("M")).sum()
        monthly.index = monthly.index.to_timestamp()
        r = run_forecast(_resp(4), monthly, date(2024, 6, 30), 4, {}, lambda: daily)
        self.assertEqual(r.status, "ok", r.reason)
        self.assertEqual(r.model_kind, "daily")
        self.assertEqual([p.period for p in r.forecast], ["2024-07", "2024-08", "2024-09", "2024-10"])
        self.assertIn("weekly totals", r.backtest.holdout)
        _assert_bands(self, r.forecast)

    def test_trimming_partial_last_and_sparse_leading(self):
        s = trend_series(20).copy()
        s.iloc[0], s.iloc[1], s.iloc[2] = 3.0, 900.0, 0.0   # sparse, isolated, empty -> all before the first run of 3
        clean, notes = trim_monthly(s, last_date=date(2022, 8, 15))  # last month 2022-08 is partial
        self.assertEqual(clean.index[0], pd.Timestamp("2021-04-01"))
        self.assertEqual(clean.index[-1], pd.Timestamp("2022-07-01"))
        self.assertTrue(any("2022-08" in n and "partial" in n for n in notes))
        self.assertTrue(any("2021-01, 2021-02, 2021-03" in n for n in notes))
        clean2, notes2 = trim_monthly(s, last_date=date(2022, 8, 31))  # complete last month kept
        self.assertEqual(clean2.index[-1], pd.Timestamp("2022-08-01"))

    def test_repeated_calls_identical(self):
        a = run_forecast(_resp(), trend_series(), None, 3, {}).model_dump(exclude={"generated_at"})
        b = run_forecast(_resp(), trend_series(), None, 3, {}).model_dump(exclude={"generated_at"})
        self.assertEqual(a, b)
        days = pd.date_range("2024-01-01", "2024-05-31", freq="D")
        daily = pd.Series(100 + np.random.default_rng(5).normal(0, 5, len(days)), index=days)
        m = daily.groupby(daily.index.to_period("M")).sum()
        m.index = m.index.to_timestamp()
        c = run_forecast(_resp(), m, None, 3, {}, lambda: daily).model_dump(exclude={"generated_at"})
        d = run_forecast(_resp(), m, None, 3, {}, lambda: daily).model_dump(exclude={"generated_at"})
        self.assertEqual(c, d)  # simulation uses a fixed seed

    def test_anomaly_exclusion_adjusts_history(self):
        s = trend_series()
        spike_day = date(2022, 11, 25)
        s.loc[pd.Timestamp("2022-11-01")] += 5000
        items = [AnomalyItem(metric="m", dimension="overall", period=spike_day.isoformat(), observed=5200, expected=200,
                             deviation_score=9, severity="high", direction="spike", method="rolling_zscore"),
                 AnomalyItem(metric="m", dimension="overall", period=spike_day.isoformat(), observed=5200, expected=150,
                             deviation_score=9, severity="high", direction="spike", method="stl_residual"),
                 AnomalyItem(metric="m", dimension="overall", period="2022-01-03", observed=1, expected=1,
                             deviation_score=9, severity="low", direction="spike", method="isolation_forest")]
        deltas = anomaly_deltas(items)
        self.assertEqual(deltas, {spike_day: 5000.0})  # z-score preferred, IsolationForest ignored
        resp = _resp(exclude=True)
        resp.excluded_days = len(deltas)
        r = run_forecast(resp, s, None, 3, deltas)
        nov = next(h for h in r.history if h.period == "2022-11")
        self.assertIsNotNone(nov.raw_value)
        self.assertAlmostEqual(nov.raw_value - nov.value, 5000.0, places=1)
        self.assertTrue(any("1 flagged anomaly day" in n for n in r.notes))

    def test_all_zero_series_refused(self):
        r = run_forecast(_resp(), pd.Series(0.0, index=MONTHS[:20]), None, 3, {})
        self.assertEqual(r.status, "refused")

    def test_horizon_clamped_and_rules_documented(self):
        self.assertEqual(clamp_horizon(None), 3)
        self.assertEqual(clamp_horizon(0), 1)
        self.assertEqual(clamp_horizon(99), 6)
        for k in ("sparse_leading_pct", "min_months", "min_days", "refuse_mape", "good_mape", "fair_mape", "seed"):
            self.assertIn(k, FORECAST_RULES)

    def test_no_llm_in_module(self):
        src = inspect.getsource(fs)
        for banned in ("gemini", "genai", "text_to_sql", "AIService"):
            self.assertNotIn(banned, src)


class TestOlistForecast(unittest.TestCase):

    def setUp(self):
        OlistForecastService.clear_cache()
        rows = [{"month": "2016-09-01", "gross_revenue": 143.0, "total_orders": 1},
                {"month": "2016-10-01", "gross_revenue": 46490.0, "total_orders": 265}]
        rows += [{"month": m.strftime("%Y-%m-%d"), "gross_revenue": float(v), "total_orders": int(v / 160)}
                 for m, v in zip(pd.date_range("2017-01-01", periods=20, freq="MS"),
                                 100000 + 40000 * np.arange(20) + np.random.default_rng(2).normal(0, 8000, 20))]
        patch("backend.app.services.analytics_service.AnalyticsService.fetch_revenue_trend", return_value=rows).start()
        patch.object(OlistForecastService, "_last_date", return_value=date(2018, 8, 29)).start()

    def tearDown(self):
        patch.stopall()
        OlistForecastService.clear_cache()

    def test_olist_forecast(self):
        r = OlistForecastService.forecast("gross_revenue", 3, False)
        self.assertEqual(r.currency, "R$")
        self.assertEqual(r.status, "ok", r.reason)
        self.assertEqual(r.training_window, "2017-01 to 2018-07 (19 months)")
        self.assertTrue(any("2018-08" in n for n in r.notes))
        self.assertTrue(any("2016-09" in n for n in r.notes))
        self.assertEqual([p.period for p in r.forecast], ["2018-08", "2018-09", "2018-10"])
        _assert_bands(self, r.forecast)
        self.assertTrue(OlistForecastService.forecast("gross_revenue", 3, False).cached)
        self.assertIsNone(OlistForecastService.forecast("order_count", 3, False).currency)

    def test_bad_metric(self):
        with self.assertRaises(FileValidationError):
            OlistForecastService.forecast("aov", 3, False)  # not a SUM/COUNT metric


class _DatasetBase(unittest.TestCase):
    def setUp(self):
        WorkspaceCache.invalidate()

        def _profile_checked(dataset_id, owner_token=None):
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()

        patch(f"{WS}.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        patch(f"{WS}.DatasetSemanticService.get_semantic", return_value=_semantic()).start()
        self.sql_seen = []
        months = pd.date_range("2022-01-01", periods=24, freq="MS")
        vals = 5000 + 300 * np.arange(24) + np.random.default_rng(4).normal(0, 100, 24)

        def _exec(sql, schema):  # the real SQLValidator runs first (DatasetDashboardService._run)
            self.sql_seen.append(sql)
            return [{"period": m.strftime("%Y-%m-%d"), "value": float(v), "last_ts": (m + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d 18:00:00")}
                    for m, v in zip(months, vals)]
        patch("backend.app.services.dataset_dashboard_service.DatasetInsightsService.execute_guarded_sql_in_schema",
              side_effect=_exec).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()


class TestDatasetForecast(_DatasetBase):

    def test_forecast_uses_scoped_validated_sql_and_no_currency(self):
        r = DatasetForecastService.forecast("ds-dash-1", "tok-A")
        self.assertEqual(r.metric, "orders.total_amount")
        self.assertIsNone(r.currency)
        self.assertEqual(r.status, "ok", r.reason)
        self.assertEqual(r.model_kind, "monthly")
        self.assertIn("LIMIT", self.sql_seen[0])                 # validator-applied row cap
        self.assertIn("DATE_TRUNC('MONTH'", self.sql_seen[0].upper())
        self.assertNotIn("orders.customer_rating", [m.key for m in r.metrics])  # AVG measures are not offered
        _assert_bands(self, r.forecast)

    def test_owner_isolation(self):
        DatasetForecastService.forecast("ds-dash-1", "tok-A")
        for tok in ("tok-B", None):
            with self.assertRaises(FileValidationError) as ctx:
                DatasetForecastService.forecast("ds-dash-1", tok)  # cached entry never served to another token
            self.assertEqual(ctx.exception.status_code, 403)

    def test_no_time_column_is_refused_not_500(self):
        r = DatasetForecastService.forecast("ds-dash-1", "tok-A", metric="customers.*")
        self.assertEqual(r.status, "refused")
        self.assertIn("no date/time column", r.reason)

    def test_non_additive_metric_rejected(self):
        with self.assertRaises(FileValidationError) as ctx:
            DatasetForecastService.forecast("ds-dash-1", "tok-A", metric="orders.customer_rating")
        self.assertEqual(ctx.exception.status_code, 400)


class TestForecastEndpoints(_DatasetBase):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def test_dataset_endpoint_owner_token(self):
        path = "/api/datasets/ds-dash-1/forecast"
        r = self.client.get(path, headers={"X-Owner-Token": "tok-B"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("Access denied", r.json()["detail"])
        self.assertEqual(self.client.get(path).status_code, 403)
        ok = self.client.get(path + "?horizon=6", headers={"X-Owner-Token": "tok-A"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(len(ok.json()["forecast"]), 6)

    def test_horizon_validated(self):
        r = self.client.get("/api/datasets/ds-dash-1/forecast?horizon=9", headers={"X-Owner-Token": "tok-A"})
        self.assertEqual(r.status_code, 422)

    def test_olist_endpoint_bad_metric(self):
        self.assertEqual(self.client.get("/api/forecast?metric=aov").status_code, 400)

    def test_rate_limited(self):
        from backend.app.routers import datasets, forecast
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_FORECAST)\ndef get_forecast(", open(forecast.__file__).read())
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_FORECAST)\ndef get_dataset_forecast(", open(datasets.__file__).read())


if __name__ == "__main__":
    unittest.main()
