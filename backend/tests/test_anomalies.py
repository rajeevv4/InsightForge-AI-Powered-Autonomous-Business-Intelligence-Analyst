import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.main import app
from backend.app.services.anomaly_service import (
    AnomalyService,
    KNOWN_EVENTS,
    format_known_event
)
from backend.app.services.ai_service import AIService
from backend.app.exceptions import DatabaseUnavailableError

client = TestClient(app)


class TestAnomalyDetectionMethods(unittest.TestCase):
    """
    Unit test suite covering deterministic anomaly detection algorithms:
    - (a) Rolling MAD robust z-score (flat, spike, drop, Black Friday event candidate)
    - (b) STL decomposition residual outliers
    - (c) IQR dimension slice outliers
    - (d) IsolationForest multivariate detection & stable series safeguard
    """

    def setUp(self):
        os.environ["USE_FIXTURES"] = "1"

    def test_flat_series_zero_anomalies(self):
        """A completely flat series must yield exactly 0 statistical anomalies."""
        dates = pd.date_range("2017-06-01", periods=30, freq="D")
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "gross_revenue": [100.0] * 30
        })
        anomalies = AnomalyService.detect_rolling_zscore(
            df=df,
            metric="gross_revenue",
            threshold=3.0,
            window=7
        )
        self.assertEqual(len(anomalies), 0, "Flat series should yield 0 anomalies")

    def test_injected_spike(self):
        """An injected massive spike in time series must be detected with direction='spike'."""
        dates = pd.date_range("2017-07-01", periods=40, freq="D")
        vals = [1000.0] * 40
        vals[20] = 15000.0  # Massive spike at day 20
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "gross_revenue": vals
        })
        anomalies = AnomalyService.detect_rolling_zscore(
            df=df,
            metric="gross_revenue",
            threshold=2.5,
            window=7
        )
        spikes = [a for a in anomalies if a.direction == "spike"]
        self.assertGreaterEqual(len(spikes), 1, "Injected spike must be detected")
        self.assertEqual(spikes[0].period, dates[20].strftime("%Y-%m-%d"))
        self.assertEqual(spikes[0].observed, 15000.0)
        self.assertEqual(spikes[0].severity, "high")

    def test_injected_drop(self):
        """An injected severe drop in time series must be detected with direction='drop'."""
        dates = pd.date_range("2017-07-01", periods=40, freq="D")
        vals = [1000.0] * 40
        vals[30] = 10.0  # Severe drop at day 30
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "gross_revenue": vals
        })
        anomalies = AnomalyService.detect_rolling_zscore(
            df=df,
            metric="gross_revenue",
            threshold=2.5,
            window=7
        )
        drops = [a for a in anomalies if a.direction == "drop"]
        self.assertGreaterEqual(len(drops), 1, "Injected drop must be detected")
        self.assertEqual(drops[0].period, dates[30].strftime("%Y-%m-%d"))
        self.assertEqual(drops[0].observed, 10.0)

    def test_black_friday_known_event_candidate(self):
        """Black Friday peak (2017-11-24) must be tagged with known_event_candidate."""
        dates = pd.date_range("2017-11-01", periods=30, freq="D")
        vals = [25000.0] * 30
        bf_idx = 23  # Nov 24
        vals[bf_idx] = 176940.50
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "gross_revenue": vals
        })
        anomalies = AnomalyService.detect_rolling_zscore(
            df=df,
            metric="gross_revenue",
            threshold=2.5,
            window=7
        )
        bf_anomaly = next((a for a in anomalies if a.period == "2017-11-24"), None)
        self.assertIsNotNone(bf_anomaly, "Black Friday anomaly must be detected")
        self.assertIsNotNone(bf_anomaly.known_event_candidate)
        self.assertIn("Black Friday 2017", bf_anomaly.known_event_candidate)
        self.assertIn("promotional_peak", bf_anomaly.known_event_candidate)

    def test_stl_residual_detection(self):
        """STL decomposition must isolate residual outlier in seasonal series."""
        dates = pd.date_range("2017-01-01", periods=60, freq="D")
        # 7-day seasonality + baseline
        base_vals = [500.0 + (i % 7) * 60.0 for i in range(60)]
        base_vals[35] += 9000.0  # Residual shock at index 35
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "order_count": base_vals
        })
        anomalies = AnomalyService.detect_stl_residuals(
            df=df,
            metric="order_count",
            period=7,
            threshold=2.5
        )
        self.assertGreaterEqual(len(anomalies), 1)
        found = any(a.period == dates[35].strftime("%Y-%m-%d") for a in anomalies)
        self.assertTrue(found, "STL must isolate the residual shock at index 35")

    def test_iqr_slice_outlier(self):
        """IQR method must detect upper concentration outliers in dimension slices."""
        anomalies = AnomalyService.detect_iqr_dimension_slices(metric="gross_revenue", threshold=1.5)
        self.assertGreaterEqual(len(anomalies), 1, "IQR should identify slice outliers")
        self.assertTrue(any(a.method == "iqr_dimension" for a in anomalies))

    def test_isolation_forest_multivariate_detection(self):
        """IsolationForest must detect abnormal multidimensional daily vectors."""
        dates = pd.date_range("2017-05-01", periods=50, freq="D")
        daily_records = []
        for i, d in enumerate(dates):
            rev = 25000.0
            cnt = 150.0
            aov = 166.6
            ontime = 92.0
            if i == 25:
                # Highly anomalous multivariate vector
                rev = 250000.0
                cnt = 2.0
                aov = 125000.0
                ontime = 10.0
            daily_records.append({
                "period": d.strftime("%Y-%m-%d"),
                "gross_revenue": rev,
                "order_count": cnt,
                "aov": aov,
                "on_time_delivery_rate": ontime
            })
        df = pd.DataFrame(daily_records)
        anomalies = AnomalyService.detect_isolation_forest(df, contamination=0.03)
        self.assertGreaterEqual(len(anomalies), 1)
        target_date = dates[25].strftime("%Y-%m-%d")
        found = any(a.period == target_date for a in anomalies)
        self.assertTrue(found, "IsolationForest must detect the multivariate outlier")

    def test_isolation_forest_stable_series_zero_medium_high(self):
        """
        A long stable synthetic series must produce zero medium/high anomalies.
        Stand-alone IsolationForest outliers are marked 'low' unless another method agrees.
        """
        np.random.seed(123)
        dates = pd.date_range("2017-01-01", periods=100, freq="D")
        # Extremely stable metrics without spikes or drops
        df = pd.DataFrame({
            "period": dates.strftime("%Y-%m-%d"),
            "gross_revenue": 20000.0 + np.random.normal(0, 100, 100),
            "order_count": 120 + np.random.normal(0, 2, 100).astype(int),
            "aov": 166.0 + np.random.normal(0, 1, 100),
            "on_time_delivery_rate": 93.0 + np.random.normal(0, 0.5, 100)
        })
        # Stand-alone detection without confirmation
        iso_anomalies = AnomalyService.detect_isolation_forest(df, contamination=0.03)
        medium_high_iso = [a for a in iso_anomalies if a.severity in ("medium", "high")]
        self.assertEqual(
            len(medium_high_iso),
            0,
            "Stand-alone IsolationForest on stable data must produce zero medium/high anomalies"
        )


class TestAnomalyEndpoints(unittest.TestCase):
    """
    API integration and error boundary tests:
    - 503 response when DB is down without USE_FIXTURES
    - 200 response in fixture mode
    - AI natural language intent classification
    """

    def test_db_down_without_use_fixtures_returns_503(self):
        """When DB is down and USE_FIXTURES=0, endpoints must return HTTP 503 'Database unavailable'."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch(
                "backend.app.services.anomaly_service.AnomalyService.get_time_series",
                side_effect=DatabaseUnavailableError("Database unreachable")
            ):
                response = client.get("/api/anomalies?metric=gross_revenue")
                self.assertEqual(response.status_code, 503)
                self.assertIn("Database unavailable", response.json()["detail"])

                scan_res = client.post("/api/anomalies/scan", json={"grain": "daily"})
                self.assertEqual(scan_res.status_code, 503)
                self.assertIn("Database unavailable", scan_res.json()["detail"])

    def test_fixture_mode_returns_200(self):
        """In fixture mode (USE_FIXTURES=1), GET /api/anomalies returns 200 with complete payload."""
        with patch.dict(os.environ, {"USE_FIXTURES": "1"}):
            response = client.get("/api/anomalies?metric=gross_revenue&grain=daily")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["metric"], "gross_revenue")
            self.assertEqual(data["grain"], "daily")
            self.assertIn("anomalies", data)
            self.assertIn("time_series", data)
            self.assertGreater(len(data["anomalies"]), 0)
            self.assertGreater(len(data["time_series"]), 0)

    def test_ai_intent_classification_for_anomalies(self):
        """Natural language questions about outliers and spikes map to 'anomaly_detection'."""
        queries = [
            "Are there any unusual spikes in sales?",
            "Did we detect any statistical anomalies or abnormal patterns?",
            "Was there a huge sales surge on Black Friday?",
            "Show me abnormal drops or spikes across daily revenue",
            "What are the most severe outlier events in our transaction history?"
        ]
        for q in queries:
            res = AIService.classify_intent_heuristic(q)
            self.assertEqual(
                res["intent"],
                "anomaly_detection",
                f"Query '{q}' should classify as anomaly_detection"
            )


if __name__ == "__main__":
    unittest.main()
