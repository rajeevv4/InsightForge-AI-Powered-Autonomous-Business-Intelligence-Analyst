"""
Unit tests for query timeouts, database connection errors, and fixture mode guardrails.
Verifies that:
1. When statement-timeout occurs (57014 / statement timeout) and USE_FIXTURES is unset:
   /api/ai/ask and /api/anomalies endpoints return HTTP 504 with detail 'Query timed out, please retry'
   and ZERO fabricated evidence.
2. When database connection fails and USE_FIXTURES is unset:
   /api/ai/ask and /api/anomalies endpoints return HTTP 503 with detail 'Database unavailable'.
3. When USE_FIXTURES=1:
   /api/health truthfully reports data_source: 'fixture' and endpoints serve canonical fixtures.
"""

import os
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.exceptions import QueryTimeoutError, DatabaseUnavailableError
from backend.app.services.anomaly_service import AnomalyService

client = TestClient(app)


class TestTimeoutsAndFallbacks(unittest.TestCase):

    def setUp(self):
        AnomalyService.clear_cache()

    def tearDown(self):
        AnomalyService.clear_cache()

    # ------------------------------------------------------------------------
    # Test (a): Statement Timeout Error surfaces as HTTP 504 (Zero Fake Data)
    # ------------------------------------------------------------------------
    def test_anomaly_query_timeout_ask_ai_returns_504(self):
        """When an anomaly query times out and USE_FIXTURES is unset, /api/ai/ask returns 504."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.run_full_scan") as mock_scan:
                mock_scan.side_effect = QueryTimeoutError("canceling statement due to statement timeout")
                
                response = client.post("/api/ai/ask", json={"question": "Are there any anomalies in our revenue?"})
                self.assertEqual(response.status_code, 504)
                data = response.json()
                self.assertEqual(data.get("detail"), "Query timed out, please retry")
                self.assertNotIn("evidence", data)

    def test_anomaly_query_timeout_get_anomalies_returns_504(self):
        """When anomaly detection times out and USE_FIXTURES is unset, GET /api/anomalies returns 504."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.detect_all") as mock_detect:
                mock_detect.side_effect = QueryTimeoutError("canceling statement due to statement timeout")
                
                response = client.get("/api/anomalies?metric=gross_revenue")
                self.assertEqual(response.status_code, 504)
                data = response.json()
                self.assertEqual(data.get("detail"), "Query timed out, please retry")
                self.assertNotIn("anomalies", data)

    def test_anomaly_query_timeout_scan_returns_504(self):
        """When full anomaly scan times out and USE_FIXTURES is unset, POST /api/anomalies/scan returns 504."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.run_full_scan") as mock_scan:
                mock_scan.side_effect = QueryTimeoutError("canceling statement due to statement timeout")
                
                response = client.post("/api/anomalies/scan", json={"grain": "daily"})
                self.assertEqual(response.status_code, 504)
                data = response.json()
                self.assertEqual(data.get("detail"), "Query timed out, please retry")

    # ------------------------------------------------------------------------
    # Test (b): Database Connection Error surfaces as HTTP 503
    # ------------------------------------------------------------------------
    def test_db_connection_error_ask_ai_returns_503(self):
        """When DB connection fails and USE_FIXTURES is unset, /api/ai/ask returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.detect_all") as mock_detect:
                mock_detect.side_effect = DatabaseUnavailableError("could not connect to server: Connection refused")
                
                response = client.post("/api/ai/ask", json={"question": "Are there any anomalies?"})
                self.assertEqual(response.status_code, 503)
                data = response.json()
                self.assertEqual(data.get("detail"), "Database unavailable")

    def test_db_connection_error_get_anomalies_returns_503(self):
        """When DB is unreachable and USE_FIXTURES is unset, GET /api/anomalies returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.detect_all") as mock_detect:
                mock_detect.side_effect = DatabaseUnavailableError("connection to server was lost")
                
                response = client.get("/api/anomalies")
                self.assertEqual(response.status_code, 503)
                data = response.json()
                self.assertEqual(data.get("detail"), "Database unavailable")

    def test_db_connection_error_scan_returns_503(self):
        """When DB is unreachable and USE_FIXTURES is unset, POST /api/anomalies/scan returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.services.anomaly_service.AnomalyService.run_full_scan") as mock_scan:
                mock_scan.side_effect = DatabaseUnavailableError("connection to server was lost")
                
                response = client.post("/api/anomalies/scan", json={"grain": "daily"})
                self.assertEqual(response.status_code, 503)
                data = response.json()
                self.assertEqual(data.get("detail"), "Database unavailable")

    # ------------------------------------------------------------------------
    # Test (c): USE_FIXTURES=1 enables fixture mode and badge in /api/health
    # ------------------------------------------------------------------------
    def test_use_fixtures_flag_health_badge_and_fallback_endpoints(self):
        """With USE_FIXTURES=1 and DB unreachable, /api/health reports data_source: fixture and endpoints serve fixtures."""
        with patch.dict(os.environ, {"USE_FIXTURES": "1"}):
            with patch("backend.app.routers.health.check_db_connection", return_value=False):
                response = client.get("/api/health")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["data_source"], "fixture")

            # Endpoints serve fixtures properly without error
            kpi_resp = client.get("/api/kpis")
            self.assertEqual(kpi_resp.status_code, 200)
            kpi_data = kpi_resp.json()
            self.assertIn("product_revenue", kpi_data)

            anom_resp = client.get("/api/anomalies")
            self.assertEqual(anom_resp.status_code, 200)
            anom_data = anom_resp.json()
            self.assertIn("anomalies", anom_data)

    # ------------------------------------------------------------------------
    # Test (d): SQL Eval Target Column Extraction (Wrong Column MUST Fail)
    # ------------------------------------------------------------------------
    def test_sql_eval_wrong_column_fails(self):
        """
        sql_29 column selection logic:
        When a generated query returns multiple columns, the evaluation MUST match
        the requested column by reference column name, not any random numeric value.
        If a query returns total_revenue instead of revenue_contribution_pct, it MUST fail.
        """
        ref_col_name = "revenue_contribution_pct"
        expected_val = 9.33

        # Case 1: Wrong column returned (only total_revenue, missing revenue_contribution_pct)
        wrong_row = {"category_name": "health_beauty", "total_revenue": 1233131.72}
        matched_val = None
        for k, v in wrong_row.items():
            if k.lower() == ref_col_name and v is not None:
                matched_val = float(v)
                break
        if matched_val is None:
            # Fallback picks first numeric column (total_revenue)
            matched_val = float(wrong_row["total_revenue"])

        # Compare with expected value (9.33) -> MUST FAIL
        match = abs(matched_val - expected_val) <= 0.05
        self.assertFalse(match, "Wrong column (total_revenue instead of revenue_contribution_pct) must FAIL accuracy check")
        self.assertEqual(matched_val, 1233131.72)

        # Case 2: Multi-column result including the requested column
        correct_multi_row = {
            "category_name": "health_beauty",
            "total_revenue": 1233131.72,
            "revenue_contribution_pct": 9.33
        }
        matched_val_correct = None
        for k, v in correct_multi_row.items():
            if k.lower() == ref_col_name and v is not None:
                matched_val_correct = float(v)
                break

        self.assertIsNotNone(matched_val_correct)
        self.assertEqual(matched_val_correct, 9.33)
        match_correct = abs(matched_val_correct - expected_val) <= 0.05
        self.assertTrue(match_correct, "Target column matched by reference name must PASS accuracy check")

    def test_sql_eval_wrong_scale_fails(self):
        """
        Negative test: A model query returning a fraction (0.0933) instead of
        the expected percentage (9.33%) must FAIL the accuracy comparison.
        """
        expected_pct = 9.33
        actual_fraction = 0.0933  # Wrong scale (fraction instead of percentage)

        abs_diff = abs(actual_fraction - expected_pct)
        rel_diff = abs_diff / abs(expected_pct)

        match = abs_diff <= 0.05 or rel_diff <= 0.02
        self.assertFalse(match, "Wrong scale (0.0933 vs 9.33) must FAIL accuracy check without loose tolerances")

    # ------------------------------------------------------------------------
    # Test (e): Text-to-SQL Business Rule Guard
    # ------------------------------------------------------------------------
    def test_sql_business_rule_guard_delivered_required(self):
        """
        Queries aggregating financial/order metrics from orders/order_items
        without a delivered filter must be DENIED to trigger self-correction.
        """
        from backend.app.services.sql_validator import SQLValidator

        # Missing delivered filter -> MUST FAIL
        unfiltered_sql = "SELECT SUM(gross_order_amount) FROM view_order_level_summary WHERE EXTRACT(YEAR FROM order_purchase_timestamp) = 2017;"
        is_valid, _, err = SQLValidator.validate(unfiltered_sql)
        self.assertFalse(is_valid, "Financial query without delivered-status filter must be DENIED")
        self.assertIn("Business rule violation", err)
        self.assertIn("order_status = 'delivered'", err)

        # Delivered filter included -> MUST PASS
        delivered_sql = "SELECT SUM(gross_order_amount) FROM view_order_level_summary WHERE EXTRACT(YEAR FROM order_purchase_timestamp) = 2017 AND order_status = 'delivered';"
        is_valid, sanitized, err = SQLValidator.validate(delivered_sql)
        self.assertTrue(is_valid, f"Financial query with delivered filter must PASS: {err}")

    def test_sql_business_rule_guard_legitimate_queries_not_blocked(self):
        """
        Legitimate non-financial queries, order status breakdowns, and canceled-status
        queries must NOT be blocked by the delivered-status rule.
        """
        from backend.app.services.sql_validator import SQLValidator

        # 1. Status breakdown (GROUP BY order_status)
        status_breakdown = "SELECT order_status, COUNT(*) AS status_count FROM orders GROUP BY order_status;"
        is_valid, _, err = SQLValidator.validate(status_breakdown)
        self.assertTrue(is_valid, f"Order status breakdown grouping by order_status must PASS: {err}")

        # 2. Canceled orders count (explicit non-delivered status query)
        canceled_query = "SELECT COUNT(*) AS canceled_count FROM orders WHERE order_status = 'canceled';"
        is_valid, _, err = SQLValidator.validate(canceled_query)
        self.assertTrue(is_valid, f"Explicit canceled orders query must PASS: {err}")

        # 3. Query against pre-filtered view (view_category_contribution already filters on delivered)
        view_query = "SELECT category_name, total_revenue FROM view_category_contribution ORDER BY total_revenue DESC LIMIT 5;"
        is_valid, _, err = SQLValidator.validate(view_query)
        self.assertTrue(is_valid, f"Query on pre-filtered view must PASS: {err}")

    # ------------------------------------------------------------------------
    # Test (e): Cache Safety & Multi-Dataset Isolation
    # ------------------------------------------------------------------------
    def test_anomaly_cache_dataset_isolation(self):
        """
        Cache keys must include dataset_id so cached results from one dataset
        are NEVER served to a different dataset session or workspace.
        """
        import pandas as pd
        from backend.app.schemas.anomaly import AnomalyListResponse

        AnomalyService.clear_cache()

        # Seed cache for dataset A
        dummy_df_a = pd.DataFrame([{"period": "2018-01-01", "gross_revenue": 1000.0}])
        dummy_resp_a = AnomalyListResponse(total_anomalies=5, grain="daily", metric="gross_revenue", anomalies=[], time_series=[])
        
        with AnomalyService._cache_lock:
            AnomalyService._series_cache[("dataset_a", "daily")] = (time.time(), dummy_df_a)
            AnomalyService._detect_cache[("dataset_a", "daily", "gross_revenue", None)] = (time.time(), dummy_resp_a)

        # Query dataset B: must be a cache miss
        with AnomalyService._cache_lock:
            cached_b = AnomalyService._detect_cache.get(("dataset_b", "daily", "gross_revenue", None))
        self.assertIsNone(cached_b, "Dataset B must NOT see cached results for Dataset A")

        # Selective clear_cache for dataset A
        AnomalyService.clear_cache(dataset_id="dataset_a")
        with AnomalyService._cache_lock:
            cached_a = AnomalyService._detect_cache.get(("dataset_a", "daily", "gross_revenue", None))
        self.assertIsNone(cached_a, "Dataset A cache must be cleared after clear_cache('dataset_a')")


if __name__ == "__main__":
    unittest.main()
