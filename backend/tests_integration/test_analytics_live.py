#!/usr/bin/env python3
"""
InsightForge — Integration Analytics Test Suite (Live Database)
===============================================================
Runs against real PostgreSQL database. Skips with a clear message
if the database is unreachable or has not yet been seeded with data.
"""

import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.database import check_db_connection, engine
from sqlalchemy import text


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

    def test_live_canonical_revenue(self):
        """Verify that live database delivers canonical gross revenue 15,419,773.75 without fan-out."""
        from database.analytics import get_summary_kpis
        kpis = get_summary_kpis()
        self.assertAlmostEqual(float(kpis["total_product_revenue"]), 13221498.11, places=2)
        self.assertAlmostEqual(float(kpis["total_gross_revenue"]), 15419773.75, places=2)
        self.assertEqual(int(kpis["total_delivered_orders"]), 96478)

    def test_live_category_sum(self):
        """Verify that live database categories sum to 100% and product revenue."""
        from database.analytics import get_category_analytics
        df = get_category_analytics(top_n=100)
        total_rev = df["total_revenue"].sum()
        total_pct = df["revenue_contribution_pct"].sum()
        self.assertAlmostEqual(total_rev, 13221498.11, places=1)
        self.assertAlmostEqual(total_pct, 100.0, places=1)


if __name__ == "__main__":
    unittest.main()
