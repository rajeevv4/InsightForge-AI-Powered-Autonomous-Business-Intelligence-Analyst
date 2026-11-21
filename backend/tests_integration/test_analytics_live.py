#!/usr/bin/env python3
"""
InsightForge — Integration Analytics Test Suite (Live Database)
===============================================================
Runs against real PostgreSQL database. Skips with a clear message
if the database is unreachable or has not yet been seeded with data.
Tests canonical numbers, fan-out safety, data-quality metrics,
endpoint health/data_source, and live statistical anomaly scans.
"""

import os
import sys
import unittest
from pathlib import Path
from sqlalchemy import text
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.database import check_db_connection, engine, readonly_engine
from backend.app.main import app

def get_live_orders_count() -> int:
    try:
        if not check_db_connection():
            return 0
        with engine.connect() as conn:
            cnt = conn.execute(text("SELECT count(*) FROM insightforge.orders;")).scalar()
            return int(cnt or 0)
    except Exception:
        return 0


LIVE_ORDER_COUNT = get_live_orders_count()
NO_DATA = LIVE_ORDER_COUNT == 0


@unittest.skipIf(NO_DATA, f"Live database has no data (found {LIVE_ORDER_COUNT} orders). Seed data via `python database/seed.py` to run live integration tests.")
class TestLiveDatabaseAnalytics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure we test real database without fixture overrides
        if "USE_FIXTURES" in os.environ:
            del os.environ["USE_FIXTURES"]
        cls.client = TestClient(app)

    def test_canonical_kpis_live(self):
        """Verify all 8 canonical executive KPIs against real live PostgreSQL database."""
        from database.analytics import get_summary_kpis
        kpis = get_summary_kpis()
        
        self.assertEqual(int(kpis["total_delivered_orders"]), 96478)
        self.assertEqual(int(kpis["total_active_customers"]), 93358)
        self.assertEqual(int(kpis["total_units_sold"]), 110197)
        self.assertAlmostEqual(float(kpis["total_product_revenue"]), 13221498.11, places=2)
        self.assertAlmostEqual(float(kpis["total_freight_revenue"]), 2198275.64, places=2)
        self.assertAlmostEqual(float(kpis["total_gross_revenue"]), 15419773.75, places=2)
        self.assertAlmostEqual(float(kpis["average_order_value_aov"]), 159.83, places=2)
        self.assertAlmostEqual(float(kpis["average_csat_score"]), 4.16, places=2)

    def test_fan_out_integrity_live(self):
        """Verify that analytical views do not cause join multiplication or revenue inflation."""
        from database.analytics import get_category_analytics, get_seller_analytics, get_state_analytics
        
        # 1. Category contribution view
        df_cat = get_category_analytics(top_n=200)
        total_cat_rev = float(df_cat["total_revenue"].sum())
        total_cat_units = int(df_cat["units_sold"].sum())
        total_cat_pct = float(df_cat["revenue_contribution_pct"].sum())
        
        self.assertAlmostEqual(total_cat_rev, 13221498.11, places=1)
        self.assertEqual(total_cat_units, 110197)
        self.assertGreaterEqual(total_cat_pct, 99.8)
        self.assertLessEqual(total_cat_pct, 100.2)
        
        # 2. Seller performance view
        df_seller = get_seller_analytics(top_n=5000)
        total_seller_rev = float(df_seller["total_sales_revenue"].sum())
        total_seller_units = int(df_seller["units_sold"].sum())
        self.assertAlmostEqual(total_seller_rev, 13221498.11, places=1)
        self.assertEqual(total_seller_units, 110197)
        
        # 3. State contribution view
        df_state = get_state_analytics()
        total_state_gross = float(df_state["total_gross_revenue"].sum())
        total_state_pct = float(df_state["state_revenue_contribution_pct"].sum())
        self.assertAlmostEqual(total_state_gross, 15419773.75, places=1)
        self.assertGreaterEqual(total_state_pct, 99.8)
        self.assertLessEqual(total_state_pct, 100.2)

    def test_data_quality_endpoint_vs_direct_sql(self):
        """Verify GET /api/data-quality outputs match direct SQL PK/FK queries."""
        response = self.client.get("/api/data-quality")
        self.assertEqual(response.status_code, 200)
        dq_data = response.json()
        
        self.assertEqual(dq_data["audit_status"], "PASS")
        self.assertIn("orders", dq_data["table_row_counts"])
        self.assertEqual(dq_data["table_row_counts"]["orders"], 99441)
        self.assertEqual(dq_data["table_row_counts"]["order_items"], 112650)
        
        # Direct SQL verification of PK uniqueness
        with readonly_engine.connect() as conn:
            dup_orders = conn.execute(text(
                "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM insightforge.orders;"
            )).scalar()
            self.assertEqual(int(dup_orders or 0), 0)
            
            # Direct SQL check for FK integrity between order_items and orders
            orphan_items = conn.execute(text("""
                SELECT COUNT(*) FROM insightforge.order_items oi
                LEFT JOIN insightforge.orders o ON oi.order_id = o.order_id
                WHERE o.order_id IS NULL;
            """)).scalar()
            self.assertEqual(int(orphan_items or 0), 0)

    def test_all_get_endpoints_live(self):
        """Verify that every analytics and health GET endpoint returns 200 with non-empty data."""
        # 1. Health
        health_resp = self.client.get("/api/health")
        self.assertEqual(health_resp.status_code, 200)
        health_json = health_resp.json()
        self.assertEqual(health_json["status"], "healthy")
        self.assertEqual(health_json["database"], "connected")
        self.assertEqual(health_json["data_source"], "postgres")
        
        # 2. KPIs
        kpi_resp = self.client.get("/api/kpis")
        self.assertEqual(kpi_resp.status_code, 200)
        self.assertEqual(kpi_resp.json()["gross_revenue"], 15419773.75)
        
        # 3. Monthly Revenue Trend
        trend_resp = self.client.get("/api/analytics/revenue-trend")
        self.assertEqual(trend_resp.status_code, 200)
        self.assertGreater(len(trend_resp.json()), 15)
        
        # 4. Top Categories
        cat_resp = self.client.get("/api/analytics/categories?limit=5")
        self.assertEqual(cat_resp.status_code, 200)
        self.assertEqual(len(cat_resp.json()), 5)
        
        # 5. State Breakdown
        state_resp = self.client.get("/api/analytics/states")
        self.assertEqual(state_resp.status_code, 200)
        self.assertGreater(len(state_resp.json()), 20)
        
        # 6. Top Sellers
        seller_resp = self.client.get("/api/analytics/sellers?limit=5")
        self.assertEqual(seller_resp.status_code, 200)
        self.assertEqual(len(seller_resp.json()), 5)
        
        # 7. Delivery SLA
        deliv_resp = self.client.get("/api/analytics/delivery")
        self.assertEqual(deliv_resp.status_code, 200)
        self.assertGreater(len(deliv_resp.json()), 1)
        
        # 8. Payments Breakdown
        pay_resp = self.client.get("/api/analytics/payments")
        self.assertEqual(pay_resp.status_code, 200)
        self.assertGreater(len(pay_resp.json()), 2)
        
        # 9. Anomalies List
        anom_resp = self.client.get("/api/anomalies?grain=daily")
        self.assertEqual(anom_resp.status_code, 200)
        self.assertIn("anomalies", anom_resp.json())

    def test_live_anomaly_scan(self):
        """Verify that POST /api/anomalies/scan executes anomaly scan on real data."""
        scan_resp = self.client.post("/api/anomalies/scan", json={"grain": "daily"})
        self.assertEqual(scan_resp.status_code, 200)
        scan_data = scan_resp.json()
        self.assertEqual(scan_data["status"], "completed")
        self.assertGreater(scan_data["anomalies_detected"], 0)
        
        # Verify Black Friday 2017 detection
        bf_found = any("2017-11-24" in str(a.get("period")) for a in scan_data.get("anomalies", []))
        self.assertTrue(bf_found, "Expected Black Friday 2017 (2017-11-24) to be detected in live anomaly scan.")


if __name__ == "__main__":
    unittest.main()
