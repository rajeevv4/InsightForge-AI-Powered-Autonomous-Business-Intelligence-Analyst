"""
Unit tests for the one-click report (JSON payload + PDF).

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_report
"""

import inspect
import io
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.limiter import limiter
from backend.app.main import app
from backend.app.schemas.anomaly import AnomalyItem
from backend.app.schemas.forecast import ForecastBacktest, ForecastPoint, ForecastResponse
from backend.app.schemas.report import ReportKPI, ReportResponse
from backend.app.services import report_pdf, report_service
from backend.app.services.dataset_file_parser import FileValidationError
from backend.app.services.report_pdf import build_pdf, safe_filename
from backend.app.services.report_service import DatasetReportService, OlistReportService, clear_report_cache
from backend.tests.test_dataset_dashboard import _profile

AN = "backend.app.services.analytics_service.AnalyticsService"
KPIS = {"product_revenue": 13221498.11, "freight_revenue": 2198275.64, "gross_revenue": 15419773.75, "delivered_orders": 96478,
        "active_customers": 93358, "units_sold": 110197, "aov": 159.83, "csat": 4.16}
TREND = [{"month": f"{2017 + (i // 12)}-{(i % 12) + 1:02d}-01", "gross_revenue": 100000.0 + 10000 * i, "total_orders": 600 + 60 * i}
         for i in range(20)]
DQ = {"audit_status": "PASS", "table_row_counts": {"customers": 99441, "orders": 99441},
      "missing_value_summary": {"orders.order_approved_at": 160}, "primary_key_uniqueness": "PASS (0 duplicates)",
      "foreign_key_integrity": "PASS (0 orphans)", "domain_bounds_status": "PASS (0 out of range values)",
      "join_safety_status": "PASS (0.00 discrepancy)"}


def _anoms(n=7):
    return [AnomalyItem(metric="gross_revenue", dimension="overall", period=f"2018-01-{d:02d}", observed=1000.0 + d, expected=500.0,
                        deviation_score=float(20 - d), severity="high", direction="spike", method="rolling_zscore") for d in range(1, n + 1)]


def _forecast(status="ok", currency="R$"):
    pts = [ForecastPoint(period=f"2018-0{8 + i}" if i < 2 else "2018-10", expected=1000.0 + i, lower_80=900.0, upper_80=1100.0 + i,
                         lower_95=800.0, upper_95=1200.0 + i) for i in range(3)] if status == "ok" else []
    return ForecastResponse(dataset_id="olist-demo", dataset_name="Olist", metric="gross_revenue", metric_label="Gross revenue",
                            currency=currency, horizon=3, status=status, reliability="Fair" if status == "ok" else None,
                            reason=None if status == "ok" else "Needs at least 12 clean months.", model="ETS",
                            training_window="2017-01 to 2018-07 (19 months)", forecast=pts,
                            backtest=ForecastBacktest(holdout="last 3 months", mape=17.0, naive_mape=7.5, naive_method="naive", beats_naive=False),
                            notes=["Dropped 2018-08: partial month (data ends 2018-08-29)."])


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


class _OlistBase(unittest.TestCase):
    def setUp(self):
        clear_report_cache()
        self.patches = {
            "kpis": patch(f"{AN}.fetch_canonical_kpis", return_value=KPIS),
            "trend": patch(f"{AN}.fetch_revenue_trend", return_value=TREND),
            "cat": patch(f"{AN}.fetch_categories", return_value=[{"category": f"cat{i}", "total_revenue": 1000.0 * (12 - i)} for i in range(12)]),
            "states": patch(f"{AN}.fetch_states", return_value=[{"state": "SP", "total_gross_revenue": 600.0}, {"state": "RJ", "total_gross_revenue": 400.0}]),
            "pay": patch(f"{AN}.fetch_payments", return_value=[{"payment_type": "credit_card", "total_payment_value": 900.0}]),
            "det": patch("backend.app.services.anomaly_service.AnomalyService.detect_all",
                         return_value=SimpleNamespace(anomalies=_anoms(), total_anomalies=7, time_series=[])),
            "exp": patch("backend.app.services.anomaly_explain_service.OlistAnomalyExplainService.explain",
                         return_value=SimpleNamespace(top_drivers=[SimpleNamespace(sentence="Customer state SP contributed +R$ 450 (90% of the spike).")],
                                                      section_errors={})),
            "fc": patch("backend.app.services.forecast_service.OlistForecastService.forecast", return_value=_forecast()),
            "dq": patch("backend.app.services.data_quality_service.DataQualityService.fetch_audit_summary", return_value=DQ),
        }
        self.mocks = {k: p.start() for k, p in self.patches.items()}

    def tearDown(self):
        patch.stopall()
        clear_report_cache()


class TestOlistReport(_OlistBase):

    def test_payload_shape_and_numbers_match_services(self):
        r = OlistReportService.build()
        self.assertEqual(r.section_errors, {})
        self.assertEqual(r.currency, "R$")
        self.assertEqual(r.kpis[0].value, KPIS["gross_revenue"])          # same numbers as /api/kpis (Overview)
        self.assertEqual(r.kpis[0].display, "R$ 15,419,773.75")
        self.assertEqual(len(r.trend.points), 20)
        self.assertEqual(r.period, "2017-01 to 2018-08")
        cat = r.breakdowns[0]
        self.assertEqual(len(cat.items), 8)
        self.assertEqual(cat.other_groups, 4)
        self.assertEqual(cat.total_value, sum(1000.0 * (12 - i) for i in range(12)))
        self.assertTrue(cat.total_line.startswith("All groups total"))
        self.assertEqual(len(r.anomalies), 5)                               # top 5
        self.assertEqual(r.anomalies[0].period, "2018-01-01")               # largest |deviation| first
        self.assertIn("contributed", r.anomalies[0].driver_sentence)
        self.assertEqual(r.forecast.status, "ok")
        self.assertEqual(len(r.forecast.points), 3)
        self.assertEqual({d.status for d in r.data_quality} - {"PASS", "WARN", "FAIL"}, set())
        self.assertTrue(5 <= len(r.summary) <= 8)
        self.assertTrue(r.methodology and r.caveats)
        self.assertTrue(OlistReportService.build().cached)

    def test_summary_uses_last_full_month(self):
        r = OlistReportService.build()
        self.assertTrue(any("(2018-07)" in s for s in r.summary))  # 2018-08 is the partial month reported by the forecast

    def test_pdf_valid_three_pages_with_kpi_values(self):
        pdf = build_pdf(OlistReportService.build())
        self.assertTrue(pdf.startswith(b"%PDF"))
        reader = PdfReader(io.BytesIO(pdf))
        self.assertGreaterEqual(len(reader.pages), 3)
        text = _pdf_text(pdf)
        for k in ("R$ 15,419,773.75", "96,478", "R$ 159.83", "93,358"):
            self.assertIn(k, text)
        self.assertIn("Page 1 of", text)
        self.assertIn("All groups total", text)

    def test_failing_section_is_isolated(self):
        self.mocks["fc"].side_effect = RuntimeError("canceling statement due to statement timeout")
        self.mocks["exp"].side_effect = RuntimeError("boom")
        r = OlistReportService.build()
        self.assertIsNone(r.forecast)
        self.assertIn("timed out", r.section_errors["forecast"])
        self.assertNotIn("statement timeout", r.section_errors["forecast"])   # no driver internals
        self.assertIsNotNone(r.kpis)
        self.assertIsNotNone(r.breakdowns)
        self.assertTrue(all(a.driver_sentence.startswith("Drivers unavailable") for a in r.anomalies))
        self.assertFalse(OlistReportService.build().cached)                # degraded reports are not cached
        text = _pdf_text(build_pdf(r))
        self.assertIn("Section unavailable:", text)
        self.assertIn("R$ 15,419,773.75", text)

    def test_budget_timeout_marks_section(self):
        import time as _t

        def slow():
            _t.sleep(1.5)
            return DQ
        self.mocks["dq"].side_effect = slow
        with patch.object(report_service, "REPORT_BUDGET_SECONDS", 0.5):
            r = OlistReportService.build()
        self.assertIn("budget", r.section_errors["data_quality"])
        self.assertIsNotNone(r.kpis)

    def test_no_llm(self):
        for mod in (report_service, report_pdf):
            src = inspect.getsource(mod)
            for banned in ("gemini", "genai", "text_to_sql", "AIService"):
                self.assertNotIn(banned, src)


class TestPdfRobustness(unittest.TestCase):

    def _report(self, name):
        return ReportResponse(dataset_id="d", dataset_name=name, generated_at=datetime.now(timezone.utc), period=None,
                              row_counts={"टेबल": 3, "表": 4}, total_rows=7,
                              summary=[f"{name} has 7 rows.", "Ünïcödé — “quotes” & <tags> stay literal."],
                              kpis=[ReportKPI(label="बिक्री कुल", value=1.5, display="1.50")],
                              section_errors={"trend": "no date/time column for a monthly trend"},
                              caveats=["x"], methodology=["y"])

    def test_non_latin_text_never_crashes(self):
        name = "दुकान डेटा 店铺数据 متجر <b>&amp;"
        pdf = build_pdf(self._report(name))
        self.assertTrue(pdf.startswith(b"%PDF"))
        text = _pdf_text(pdf)
        self.assertIn("<tags>", text)                 # XML-escaped, not interpreted as markup
        self.assertIn("Section unavailable: no date/time column", text)
        self.assertEqual(safe_filename(name), f"InsightForge_Report_b_amp_{datetime.now().strftime('%Y-%m-%d')}.pdf")
        self.assertTrue(safe_filename("Shop / Q&A 2024").startswith("InsightForge_Report_Shop_Q_A_2024_"))

    def test_helvetica_fallback_never_crashes(self):
        with patch.object(report_pdf, "report_fonts", return_value=("Helvetica", "Helvetica-Bold", None)):
            pdf = build_pdf(self._report("दुकान 店铺"))
        self.assertTrue(pdf.startswith(b"%PDF"))


class TestDatasetReport(unittest.TestCase):
    """Uploaded dataset: owner check first; no time column still gives a report."""

    def setUp(self):
        clear_report_cache()

        def _profile_checked(dataset_id, owner_token=None):
            if owner_token != "tok-A":
                raise FileValidationError("Access denied. Invalid owner token for this dataset.", status_code=403)
            return _profile()
        patch("backend.app.services.dataset_service.DatasetService.get_dataset_profile", side_effect=_profile_checked).start()
        kpi = SimpleNamespace(label="Total Amount", table="orders", column="total_amount", aggregation="SUM", value=3662817.3, error=None)
        bd = SimpleNamespace(title="Total Amount by City", aggregation="SUM", other_groups=0, other_value=None, total_value=300.0,
                             items=[SimpleNamespace(label="Mumbai", value=200.0), SimpleNamespace(label="Delhi", value=100.0)])
        self.overview = SimpleNamespace(kpis=[kpi], primary_measure="orders.total_amount", trend=None, breakdowns=[bd],
                                        skipped_breakdowns=[], section_errors={"trend": "no date/time column"})
        patch("backend.app.services.dataset_workspace_service.DatasetWorkspaceService.get_overview", return_value=self.overview).start()
        patch("backend.app.services.dataset_anomaly_service.DatasetAnomalyService.get_anomalies",
              side_effect=FileValidationError("Table 'orders' has no date/time column; anomaly detection needs a time series.", status_code=400)).start()
        patch("backend.app.services.forecast_service.DatasetForecastService.forecast",
              return_value=_forecast("refused", currency=None)).start()
        dq = SimpleNamespace(audit_status="PASS", primary_key_uniqueness="PASS (0 duplicates)", foreign_key_integrity="",
                             domain_bounds_status="PASS", join_safety_status="", checks=[])
        patch("backend.app.services.dataset_workspace_service.DatasetWorkspaceQuality.get_data_quality", return_value=dq).start()

    def tearDown(self):
        patch.stopall()
        clear_report_cache()

    def test_no_time_column_still_reports(self):
        r = DatasetReportService.build("ds-dash-1", "tok-A")
        self.assertIsNone(r.currency)
        self.assertIsNone(r.period)
        self.assertIn("trend", r.section_errors)
        self.assertIn("no date/time column", r.section_errors["anomalies"])
        self.assertEqual(r.forecast.status, "refused")
        self.assertEqual(r.kpis[0].display, "3,662,817.30")
        self.assertEqual(r.breakdowns[0].total_line, "All groups total: 300")
        self.assertTrue(r.summary)
        pdf = build_pdf(r)
        text = _pdf_text(pdf)
        self.assertNotIn("R$", text)
        self.assertIn("3,662,817.30", text)

    def test_owner_isolation(self):
        DatasetReportService.build("ds-dash-1", "tok-A")
        for tok in ("tok-B", None):
            with self.assertRaises(FileValidationError) as ctx:
                DatasetReportService.build("ds-dash-1", tok)   # the cached report is never served to another token
            self.assertEqual(ctx.exception.status_code, 403)


class TestReportEndpoints(TestDatasetReport):

    def setUp(self):
        super().setUp()
        limiter.reset()
        self.client = TestClient(app)
        patch("backend.app.routers.datasets.is_fixture_mode", return_value=False).start()

    def tearDown(self):
        limiter.reset()
        super().tearDown()

    def test_dataset_endpoint_owner_token_and_pdf(self):
        path = "/api/datasets/ds-dash-1/report"
        r = self.client.get(path, headers={"X-Owner-Token": "tok-B"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("Access denied", r.json()["detail"])
        self.assertEqual(self.client.get(path).status_code, 403)
        ok = self.client.get(path + "?format=pdf", headers={"X-Owner-Token": "tok-A"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers["content-type"], "application/pdf")
        self.assertIn("InsightForge_Report_", ok.headers["content-disposition"])
        self.assertTrue(ok.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(path + "?format=xml", headers={"X-Owner-Token": "tok-A"}).status_code, 422)

    def test_rate_limited_with_detail(self):
        from backend.app.routers import datasets, report
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_REPORT)\ndef get_report(", open(report.__file__).read())
        self.assertIn("@limiter.limit(settings.RATE_LIMIT_REPORT)\ndef get_dataset_report(", open(datasets.__file__).read())
        from backend.app.config import settings
        with patch.object(limiter, "_storage", limiter._storage):
            codes = [self.client.get("/api/datasets/ds-dash-1/report", headers={"X-Owner-Token": "tok-A"}).status_code
                     for _ in range(int(settings.RATE_LIMIT_REPORT.split("/")[0]) + 1)]
        self.assertEqual(codes[-1], 429)
        last = self.client.get("/api/datasets/ds-dash-1/report", headers={"X-Owner-Token": "tok-A"})
        self.assertIn("detail", last.json())


if __name__ == "__main__":
    unittest.main()
