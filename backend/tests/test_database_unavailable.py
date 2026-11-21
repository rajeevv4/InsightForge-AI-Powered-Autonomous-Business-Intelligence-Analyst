import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import app

client = TestClient(app)


class TestDatabaseUnavailable(unittest.TestCase):
    """
    LEVEL 1.5 Tests:
    1. DB down and no USE_FIXTURES flag -> HTTP 503 "Database unavailable".
    2. /api/health truthfully reports database: "disconnected".
    3. USE_FIXTURES=1 enables fixture data and data_source: "fixture" (which triggers the DEMO DATA badge in UI).
    """

    def test_db_down_no_flag_returns_503_kpis(self):
        """When DB is unreachable and USE_FIXTURES is 0/unset, /api/kpis returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("database.analytics.get_db_engine") as mock_engine:
                mock_engine.return_value.connect.side_effect = Exception("Connection refused")
                response = client.get("/api/kpis")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Database unavailable"})

    def test_db_down_no_flag_returns_503_categories(self):
        """When DB is unreachable and USE_FIXTURES is 0/unset, /api/analytics/categories returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("database.analytics.get_db_engine") as mock_engine:
                mock_engine.return_value.connect.side_effect = Exception("Connection refused")
                response = client.get("/api/analytics/categories")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Database unavailable"})

    def test_db_down_no_flag_returns_503_data_quality(self):
        """When DB is unreachable and USE_FIXTURES is 0/unset, /api/data-quality returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("database.data_quality.get_db_engine") as mock_engine:
                mock_engine.return_value.connect.side_effect = Exception("Connection refused")
                response = client.get("/api/data-quality")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Database unavailable"})

    def test_db_down_no_flag_returns_503_ask_ai(self):
        """When DB is unreachable and USE_FIXTURES is 0/unset, /api/ai/ask returns 503."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("database.analytics.get_db_engine") as mock_engine:
                mock_engine.return_value.connect.side_effect = Exception("Connection refused")
                response = client.post("/api/ai/ask", json={"question": "What is total revenue?"})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Database unavailable"})

    def test_db_down_health_reports_truthfully_disconnected(self):
        """When DB is unreachable and no fixtures, /api/health reports database: disconnected and data_source: postgres."""
        with patch.dict(os.environ, {"USE_FIXTURES": "0"}):
            with patch("backend.app.routers.health.check_db_connection", return_value=False):
                response = client.get("/api/health")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["database"], "disconnected")
                self.assertEqual(data["data_source"], "postgres")
                self.assertEqual(data["status"], "unhealthy")

    def test_flag_set_gives_fixture_and_badge_datasource(self):
        """When DB is unreachable but USE_FIXTURES=1, /api/health reports data_source: fixture, and endpoints serve fixtures."""
        with patch.dict(os.environ, {"USE_FIXTURES": "1"}):
            with patch("backend.app.routers.health.check_db_connection", return_value=False):
                response = client.get("/api/health")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["database"], "disconnected")
                self.assertEqual(data["data_source"], "fixture")
                self.assertEqual(data["status"], "degraded")

            # With USE_FIXTURES=1, endpoints return fixture data successfully
            kpi_resp = client.get("/api/kpis")
            self.assertEqual(kpi_resp.status_code, 200)
            self.assertEqual(kpi_resp.json()["product_revenue"], 13221498.11)


if __name__ == "__main__":
    unittest.main()
