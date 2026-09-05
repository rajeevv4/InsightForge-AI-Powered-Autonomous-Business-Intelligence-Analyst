import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.main import app

client = TestClient(app)

class TestFastAPIBackend(unittest.TestCase):

    def test_health_endpoint(self):
        """Test GET /api/health returns healthy status and DB connection."""
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertEqual(data["service"], "InsightForge")

    def test_kpis_endpoint(self):
        """Test GET /api/kpis returns exact canonical metrics."""
        response = client.get("/api/kpis")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["product_revenue"], 13221498.11)
        self.assertEqual(data["freight_revenue"], 2198275.64)
        self.assertEqual(data["gross_revenue"], 15419773.75)
        self.assertEqual(data["delivered_orders"], 96478)
        self.assertEqual(data["units_sold"], 110197)
        self.assertEqual(data["aov"], 159.83)
        self.assertEqual(data["csat"], 4.16)

    def test_revenue_trend_endpoint(self):
        """Test GET /api/analytics/revenue-trend returns monthly sales trend."""
        response = client.get("/api/analytics/revenue-trend")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 10)
        self.assertIn("gross_revenue", data[0])
        self.assertIn("mom_revenue_growth_pct", data[0])

    def test_categories_endpoint(self):
        """Test GET /api/analytics/categories with limit parameter."""
        response = client.get("/api/analytics/categories?limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["category"], "health_beauty")

    def test_states_endpoint(self):
        """Test GET /api/analytics/states returns regional breakdown."""
        response = client.get("/api/analytics/states")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 20)
        self.assertEqual(data[0]["state"], "SP")

    def test_sellers_endpoint(self):
        """Test GET /api/analytics/sellers returns top sellers."""
        response = client.get("/api/analytics/sellers?limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 5)

    def test_delivery_endpoint(self):
        """Test GET /api/analytics/delivery returns SLA breakdown."""
        response = client.get("/api/analytics/delivery")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 1)

    def test_payments_endpoint(self):
        """Test GET /api/analytics/payments returns payment methods."""
        response = client.get("/api/analytics/payments")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 2)

    def test_data_quality_endpoint(self):
        """Test GET /api/data-quality returns audit summary."""
        response = client.get("/api/data-quality")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["audit_status"], "PASS")
        self.assertIn("customers", data["table_row_counts"])


def run_tests():
    print("=" * 70)
    print("        INSIGHTFORGE — FASTAPI BACKEND API TEST SUITE        ")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFastAPIBackend)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL BACKEND API TESTS PASSED SUCCESSFULLY!")
    else:
        print("❌ SOME BACKEND API TESTS FAILED!")
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
