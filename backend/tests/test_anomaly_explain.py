"""
Unit tests for "Explain this anomaly" (root-cause waterfall), Olist and uploaded datasets.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_anomaly_explain
"""

import inspect
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.anomaly import AnomalyItem, AnomalyTimeSeriesPoint
from backend.app.services import anomaly_explain_service as svc
from backend.app.services.anomaly_explain_service import (
    DatasetAnomalyExplainService,
    GroupRow,
    OlistAnomalyExplainService,
    _olist_sql,
    additive_parts,
    build_dimension,
    explanatory_power,
    fmt_change,
    fmt_value,
    mix_shift,
    parse_period,
    ratio_parts,
    volume_value_section,
)
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.dataset_workspace_service import WorkspaceCache
from backend.tests.test_dataset_dashboard import _profile, _semantic

WS = "backend.app.services.dataset_workspace_service"
EX = "backend.app.services.anomaly_explain_service"


def _item(period, observed, expected, method="rolling_zscore", metric="gross_revenue"):
    return AnomalyItem(metric=metric, dimension="overall", period=period, observed=observed, expected=expected,
                       deviation_score=9.0, severity="high", direction="spike" if observed > expected else "drop",
                       method=method)


class TestPureMaths(unittest.TestCase):

    def test_additive_waterfall_reconciles_to_headline(self):
        groups = [GroupRow("A", num_t=500, num_b=14 * 100), GroupRow("B", num_t=150, num_b=14 * 100),
                  GroupRow("C", num_t=50, num_b=14 * 50)]
        parts, e, o = additive_parts(groups, 14, expected=200.0)
        self.assertAlmostEqual(sum(p[2] for p in parts), 200.0)          # baseline mix scaled to E
        self.assertAlmostEqual(e + sum(p[3] for p in parts), o)            # E + contributions = O
        d = build_dimension("k", "Group", parts, e, o, "spike", "number", None)
        self.assertEqual(d.waterfall[0].name, "Expected")
        self.assertEqual(d.waterfall[-1].name, "Observed")
        steps = d.waterfall[1:-1]
        self.assertAlmostEqual(d.waterfall[0].end + sum(s.value for s in steps), d.waterfall[-1].end, places=3)
        for a, b in zip(steps, steps[1:]):
            self.assertAlmostEqual(a.end, b.start, places=3)               # floating steps chain correctly
        self.assertEqual(d.drivers[0].label, "A")                          # biggest push first
        self.assertEqual(d.drivers[0].sentence, "Group A contributed +420 (84% of the spike).")

    def test_all_other_and_residual(self):
        groups = [GroupRow(f"g{i}", num_t=10 + i, num_b=14 * 10) for i in range(9)]
        parts, e, o = additive_parts(groups, 14, expected=90.0)
        d = build_dimension("k", "G", parts, e, o + 5.0, "spike", "number", None, residual=5.0)
        other = next(s for s in d.waterfall if s.name == "All other")
        self.assertEqual(d.other_groups, 4)
        self.assertAlmostEqual(d.waterfall[0].end + sum(s.value for s in d.waterfall[1:-1]), d.waterfall[-1].end, places=3)
        self.assertGreater(other.value, 5.0 - 1e-9)

    def test_ratio_contributions_sum_to_rate_change(self):
        groups = [GroupRow("x", num_t=300, num_b=1000), GroupRow("y", num_t=100, num_b=1000)]
        parts, r0, r1 = ratio_parts(groups, den_t=4, den_b=20)
        self.assertAlmostEqual(r1, 100.0)
        self.assertAlmostEqual(r0, 2000 / 20)
        self.assertAlmostEqual(sum(p[3] for p in parts), r1 - r0)

    def test_volume_value_effects_sum_to_change(self):
        vv = volume_value_section(vol_t=50, vol_b=14 * 10, num_t=6000, num_b=14 * 1000, n_periods=14, expected=1000.0,
                                  volume_label="orders", value_label="average order value", unit="currency", currency="R$")
        self.assertAlmostEqual(vv.volume_effect + vv.value_effect, 6000 - 1000.0, places=6)
        self.assertEqual(vv.dominant, "volume")
        self.assertIn("R$", vv.sentences[1])

    def test_explanatory_power_and_mix_shift(self):
        self.assertEqual(explanatory_power([10, 0, 0], 10), 1.0)
        self.assertEqual(explanatory_power([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 10), 0.3)
        self.assertEqual(explanatory_power([5], 0), 0.0)
        proportional = [("a", 200.0, 100.0, 100.0), ("b", 20.0, 10.0, 10.0)]
        self.assertEqual(mix_shift(proportional), 0.0)                    # broad-based change
        concentrated = [("a", 100.0, 100.0, 0.0), ("b", 110.0, 10.0, 100.0)]
        self.assertGreater(mix_shift(concentrated), 0.3)

    def test_dimension_order_prefers_concentrated_change(self):  # rank_score = power x mix shift
        resp = svc.AnomalyExplanationResponse(dataset_id="d", dataset_name="n", metric="m", metric_label="M",
                                              period="2024-01-15", grain="daily")
        flat = [GroupRow("p", num_t=200, num_b=14 * 100), GroupRow("q", num_t=200, num_b=14 * 100)]
        conc = [GroupRow("u", num_t=100, num_b=14 * 100), GroupRow("v", num_t=300, num_b=14 * 100)]
        out = svc.assemble(resp, [("flat", "Flat", None, (True, flat, 0, 0)), ("conc", "Conc", None, (True, conc, 0, 0))],
                           (400.0, 200.0, "spike", "detector", "rolling_zscore", "high"), None, True, 14, None, "on 2024-01-15")
        self.assertEqual([d.key for d in out.dimensions], ["conc", "flat"])
        self.assertIn("volume_value", out.section_errors)                  # independent section failure

    def test_formatting(self):
        self.assertEqual(fmt_value(40210.4, "currency", "R$"), "R$ 40,210")
        self.assertEqual(fmt_value(12.5, "currency", "R$"), "R$ 12.50")
        self.assertEqual(fmt_value(40210.4, "currency", None), "40,210")   # uploaded datasets: no symbol
        self.assertEqual(fmt_change(-1200, "currency", "R$"), "-R$ 1,200")
        self.assertEqual(fmt_change(2.04, "percent"), "+2.0 pts")
        self.assertEqual(fmt_value(187.5, "count"), "187.5")

    def test_parse_period(self):
        self.assertEqual(parse_period("2017-11-24", "daily"), date(2017, 11, 24))
        self.assertEqual(parse_period("2017-11-24", "weekly"), date(2017, 11, 20))
        self.assertEqual(parse_period("2017-W47", "weekly"), date(2017, 11, 20))
        for bad in ("", "oct", "2017-13-40", "'; DROP TABLE x; --"):
            with self.assertRaises(FileValidationError):
                parse_period(bad, "daily")

    def test_no_llm_in_module(self):
        src = inspect.getsource(svc)
        for banned in ("gemini", "genai", "GeminiClient", "text_to_sql", "AIService"):
            self.assertNotIn(banned, src)


class TestOlistExplain(unittest.TestCase):

    def setUp(self):
        OlistAnomalyExplainService.clear_cache()
        self.sql_seen = []

        def _query(sql, params):
            self.sql_seen.append(sql)
            rows = [
                {"label": "SP", "is_total": 0, "rev_t": 60000, "rev_b": 14 * 12000, "orders_t": 400, "orders_b": 14 * 80,
                 "ontime_t": 380, "ontime_b": 14 * 70, "items_t": 420, "items_b": 14 * 85, "score_t": 1600, "score_b": 14 * 320, "scoren_t": 400, "scoren_b": 14 * 80},
                {"label": "RJ", "is_total": 0, "rev_t": 20000, "rev_b": 14 * 8000, "orders_t": 120, "orders_b": 14 * 50,
                 "ontime_t": 100, "ontime_b": 14 * 45, "items_t": 130, "items_b": 14 * 52, "score_t": 480, "score_b": 14 * 200, "scoren_t": 120, "scoren_b": 14 * 50},
                {"label": None, "is_total": 1, "rev_t": 80000, "rev_b": 14 * 20000, "orders_t": 520, "orders_b": 14 * 130,
                 "ontime_t": 480, "ontime_b": 14 * 115, "items_t": 550, "items_b": 14 * 137, "score_t": 2080, "score_b": 14 * 520, "scoren_t": 520, "scoren_b": 14 * 130},
            ]
            return rows
        patch(f"{EX}.is_fixture_mode_allowed", return_value=False).start()
        patch.object(OlistAnomalyExplainService, "_query", side_effect=_query).start()
        det = SimpleNamespace(anomalies=[_item("2017-11-24", 80000.0, 21000.0)],
                              time_series=[AnomalyTimeSeriesPoint(period="2017-11-24", observed=80000.0, expected=21000.0)])
        patch("backend.app.services.anomaly_service.AnomalyService.detect_all", return_value=det).start()

    def tearDown(self):
        patch.stopall()
        OlistAnomalyExplainService.clear_cache()

    def test_revenue_explanation(self):
        r = OlistAnomalyExplainService.explain("gross_revenue", "2017-11-24", "daily")
        self.assertEqual(r.currency, "R$")
        self.assertEqual(r.headline.source, "detector")
        self.assertEqual(r.headline.direction, "spike")
        self.assertTrue(r.headline.sentence.startswith("Gross revenue was R$ 80,000 on 2017-11-24 vs R$ 21,000 expected"))
        self.assertEqual(len(r.dimensions), 4)
        for d in r.dimensions:
            wf = d.waterfall
            self.assertAlmostEqual(wf[0].end, 21000.0)
            self.assertAlmostEqual(wf[0].end + sum(s.value for s in wf[1:-1]), wf[-1].end, places=2)
        self.assertIsNotNone(r.volume_value)
        self.assertAlmostEqual(r.volume_value.volume_effect + r.volume_value.value_effect, 80000 - 21000.0, places=2)
        self.assertTrue(r.top_drivers)
        self.assertTrue(OlistAnomalyExplainService.explain("gross_revenue", "2017-11-24", "daily").cached)

    def test_fan_out_rules_in_sql(self):
        OlistAnomalyExplainService.explain("gross_revenue", "2017-11-24", "daily")
        joined = "\n".join(self.sql_seen)
        self.assertIn("order_status = 'delivered'", joined)
        self.assertIn("pay.payment_sequential = 1", joined)                          # primary payment only
        self.assertIn("GROUP BY oi.order_id", _olist_sql("state", "day"))             # items pre-aggregated per order
        self.assertIn("GROUP BY rr.order_id", _olist_sql("payment_type", "day"))      # reviews pre-aggregated per order
        self.assertNotIn("order_reviews", _olist_sql("state", "day", need_reviews=False))  # only when needed
        for d in ("category", "seller", "state", "payment_type"):
            self.assertNotIn("{", _olist_sql(d, "day"))

    def test_order_count_skips_item_level_dimensions(self):
        r = OlistAnomalyExplainService.explain("order_count", "2017-11-24", "daily")
        self.assertEqual({d.key for d in r.dimensions}, {"state", "payment_type"})
        self.assertEqual({s.dimension for s in r.skipped_dimensions}, {"Category", "Seller"})

    def test_ratio_metric_uses_trailing_level(self):
        r = OlistAnomalyExplainService.explain("aov", "2017-11-24", "daily")
        self.assertFalse(r.additive)
        d = r.dimensions[0]
        self.assertEqual(d.waterfall[0].name, "Trailing avg")
        self.assertAlmostEqual(d.waterfall[-1].end, 80000 / 520, places=3)
        self.assertIn("volume_value", r.section_errors)

    def test_bad_inputs(self):
        for kwargs in ({"metric": "nope", "period": "2017-11-24"}, {"metric": "aov", "period": "2030-01-01"},
                       {"metric": "aov", "period": "2017-11-24", "grain": "hourly"}):
            with self.assertRaises(FileValidationError):
                OlistAnomalyExplainService.explain(**kwargs)

    def test_one_failed_dimension_does_not_fail_the_payload(self):
        orig = OlistAnomalyExplainService._query.side_effect

        def flaky(sql, params):
            if "payment_sequential" in sql:
                raise RuntimeError("canceling statement due to statement timeout")
            return orig(sql, params)
        OlistAnomalyExplainService._query.side_effect = flaky
        r = OlistAnomalyExplainService.explain("gross_revenue", "2017-11-25", "daily")
        self.assertEqual(len(r.dimensions), 3)
        self.assertTrue(any(s.dimension == "Payment type" for s in r.skipped_dimensions))


class _DatasetExplainBase(unittest.TestCase):
    def setUp(self):
        WorkspaceCache.invalidate()
        self.sql_seen = []

        def _profile_checked(dataset_id, owner_token=None):
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()

        patch(f"{WS}.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        patch(f"{WS}.DatasetSemanticService.get_semantic", return_value=_semantic()).start()

        def _exec(sql, schema):  # real SQLValidator runs before this (DatasetDashboardService._run)
            self.sql_seen.append(sql)
            if "AS label" in sql or "as label" in sql.lower():
                return [{"label": "UPI", "num_t": 3000.0, "num_b": 14 * 500.0, "vol_t": 3, "vol_b": 14 * 1},
                        {"label": "Cash", "num_t": 1000.0, "num_b": 14 * 500.0, "vol_t": 1, "vol_b": 14 * 1}]
            return [{"num_t": 4000.0, "num_b": 14 * 1000.0, "vol_t": 4, "vol_b": 28, "first_p": "2024-01-01"}]
        patch("backend.app.services.dataset_dashboard_service.DatasetInsightsService.execute_guarded_sql_in_schema",
              side_effect=_exec).start()
        det = SimpleNamespace(anomalies=[_item("2024-03-01", 4000.0, 1000.0, metric="orders.total_amount")], time_series=[])
        patch("backend.app.services.dataset_anomaly_service.DatasetAnomalyService.get_anomalies", return_value=det).start()

    def tearDown(self):
        patch.stopall()
        WorkspaceCache.invalidate()


class TestDatasetExplain(_DatasetExplainBase):

    def test_explanation_uses_validated_scoped_sql_and_no_currency(self):
        r = DatasetAnomalyExplainService.explain("ds-dash-1", "tok-A", "orders.total_amount", "2024-03-01")
        self.assertIsNone(r.currency)
        self.assertNotIn("R$", r.headline.sentence + " ".join(t.sentence for t in r.top_drivers))
        self.assertEqual(r.headline.expected, 1000.0)
        keys = {d.key for d in r.dimensions}
        self.assertIn("orders.payment_method", keys)
        self.assertIn("customers.city", keys)                              # confirmed N:1 join
        for d in r.dimensions:
            wf = d.waterfall
            self.assertAlmostEqual(wf[0].end + sum(s.value for s in wf[1:-1]), wf[-1].end, places=3)
        joined = "\n".join(self.sql_seen)
        self.assertIn("LEFT JOIN", joined)
        self.assertIn("LIMIT", joined)                                     # validator-applied row cap
        self.assertIsNotNone(r.volume_value)

    def test_unconfirmed_relationship_is_skipped_not_joined(self):
        with patch(f"{WS}.DatasetService.get_dataset_profile", return_value=_profile(confirmed=False)):
            r = DatasetAnomalyExplainService.explain("ds-dash-1", "tok-A", "orders.total_amount", "2024-03-02")
        self.assertNotIn("customers.city", {d.key for d in r.dimensions})
        self.assertTrue(any("not confirmed" in s.reason for s in r.skipped_dimensions))
        self.assertNotIn("JOIN", "\n".join(self.sql_seen))

    def test_owner_check_and_cache_isolation(self):
        DatasetAnomalyExplainService.explain("ds-dash-1", "tok-A", None, "2024-03-01")
        with self.assertRaises(FileValidationError) as ctx:
            DatasetAnomalyExplainService.explain("ds-dash-1", "tok-B", None, "2024-03-01")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_avg_measure_is_ratio(self):
        r = DatasetAnomalyExplainService.explain("ds-dash-1", "tok-A", "orders.customer_rating", "2024-03-01")
        self.assertFalse(r.additive)
        self.assertIn("volume_value", r.section_errors)


class TestExplainEndpoints(_DatasetExplainBase):

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def test_owner_token_enforced(self):
        path = "/api/datasets/ds-dash-1/anomalies/explain?period=2024-03-01"
        r = self.client.get(path, headers={"X-Owner-Token": "tok-B"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("Access denied", r.json()["detail"])
        self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.get(path, headers={"X-Owner-Token": "tok-A"}).status_code, 200)

    def test_bad_period_is_400(self):
        r = self.client.get("/api/datasets/ds-dash-1/anomalies/explain?period=yesterday", headers={"X-Owner-Token": "tok-A"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("detail", r.json())

    def test_olist_endpoint_validation(self):
        r = self.client.get("/api/anomalies/explain?metric=nope&period=2017-11-24")
        self.assertEqual(r.status_code, 400)

    def test_endpoints_are_rate_limited(self):
        from backend.app.routers import anomalies, datasets
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_ANOMALY_EXPLAIN)\ndef explain_anomaly(", open(anomalies.__file__).read())
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_ANOMALY_EXPLAIN)\ndef explain_dataset_anomaly(", open(datasets.__file__).read())

    def test_429_body_has_detail(self):
        from backend.app.main import rate_limit_handler
        from slowapi.errors import RateLimitExceeded
        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(limiter=SimpleNamespace(_inject_headers=lambda r, _l: r))),
                              state=SimpleNamespace(view_rate_limit=None))
        exc = RateLimitExceeded.__new__(RateLimitExceeded)
        exc.detail = "30 per 1 minute"
        res = rate_limit_handler(req, exc)
        self.assertEqual(res.status_code, 429)
        import json
        body = json.loads(res.body)
        self.assertIn("detail", body)
        self.assertIn("error", body)  # slowapi's original key kept


if __name__ == "__main__":
    unittest.main()
