"""
Determinism tests for AnomalyService.detect_all severity calibration.

Regression: run_full_scan() used to write into detect_all's cache and then re-calibrate
the cached AnomalyItem objects in place, so the Anomalies page's high-severity count
changed (e.g. 7 -> 2) after a scan while the total stayed the same.

Run: USE_FIXTURES=1 python -m unittest backend.tests.test_anomaly_determinism
"""

import os
import unittest

from backend.app.services.anomaly_service import AnomalyService


def _snapshot(resp):
    """(high count, {period: severity}, slice outlier count) for overall time-series items."""
    sev = {(a.metric, a.dimension, a.period, a.method): a.severity for a in resp.anomalies}
    high = sum(1 for a in resp.anomalies if a.severity == "high")
    return high, sev, len(resp.slice_outliers)


class TestAnomalyDeterminism(unittest.TestCase):

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

    def test_repeated_calls_identical(self):
        base = _snapshot(AnomalyService.detect_all(grain="daily", metric="gross_revenue"))
        for _ in range(3):
            AnomalyService.clear_cache()  # force recomputation, not just a cache hit
            self.assertEqual(_snapshot(AnomalyService.detect_all(grain="daily", metric="gross_revenue")), base)

    def test_severity_filters_are_consistent(self):
        """Whatever filter is requested first, each period gets the same severity."""
        for order in ([None, "high", "medium"], ["high", "medium", None], ["medium", None, "high"]):
            AnomalyService.clear_cache()
            results = {f: AnomalyService.detect_all(grain="daily", metric="gross_revenue", severity=f) for f in order}
            full = {(a.metric, a.dimension, a.period, a.method): a.severity for a in results[None].anomalies}
            for f in ("high", "medium"):
                for a in results[f].anomalies:
                    self.assertEqual(a.severity, f)
                    self.assertEqual(full[(a.metric, a.dimension, a.period, a.method)], f)
                self.assertEqual(len(results[f].anomalies), sum(1 for s in full.values() if s == f))

    def test_full_scan_does_not_change_detect_all_results(self):
        before = _snapshot(AnomalyService.detect_all(grain="daily", metric="gross_revenue"))
        AnomalyService.run_full_scan(grain="daily")
        after_cached = _snapshot(AnomalyService.detect_all(grain="daily", metric="gross_revenue"))
        self.assertEqual(after_cached, before, "full scan mutated/overwrote detect_all's cached results")
        AnomalyService.clear_cache()
        after_fresh = _snapshot(AnomalyService.detect_all(grain="daily", metric="gross_revenue"))
        self.assertEqual(after_fresh, before)

    def test_full_scan_high_count_matches_detect_all(self):
        """The scan banner and the page must agree on gross_revenue high-severity periods."""
        page_high = {a.period for a in AnomalyService.detect_all(grain="daily", metric="gross_revenue").anomalies
                     if a.severity == "high"}
        scan = AnomalyService.run_full_scan(metrics=["gross_revenue"], grain="daily")
        scan_high = {a.period for a in scan.anomalies if a.severity == "high"}
        self.assertEqual(scan_high, page_high)


if __name__ == "__main__":
    unittest.main()
