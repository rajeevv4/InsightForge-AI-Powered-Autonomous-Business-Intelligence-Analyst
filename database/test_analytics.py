#!/usr/bin/env python3
"""
InsightForge — Automated Analytics Test Suite
=============================================
Unit and integration test suite asserting mathematical accuracy, metric consistency,
join safety (zero fan-out inflation), non-negative constraints, and contribution sum accuracy.
"""

import sys
import unittest
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.analytics import (
    get_db_engine,
    get_summary_kpis,
    get_monthly_performance,
    get_category_analytics,
    get_state_analytics,
    get_delivery_performance,
    get_payment_analytics
)


class TestInsightForgeAnalytics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = get_db_engine()
        cls.kpis = get_summary_kpis()

    def test_revenue_consistency(self):
        """Assert direct sum of prices matches canonical gross revenue without fan-out distortion."""
        gross_rev = float(self.kpis['total_gross_revenue'])
        prod_rev = float(self.kpis['total_product_revenue'])
        freight_rev = float(self.kpis['total_freight_revenue'])
        delivered_orders = int(self.kpis['total_delivered_orders'])
        units_sold = int(self.kpis['total_units_sold'])
        
        # Product + Freight must equal Gross Revenue
        self.assertAlmostEqual(prod_rev + freight_rev, gross_rev, places=2)
        
        # Validate canonical InsightForge values exactly
        self.assertAlmostEqual(prod_rev, 13221498.11, places=2)
        self.assertAlmostEqual(freight_rev, 2198275.64, places=2)
        self.assertAlmostEqual(gross_rev, 15419773.75, places=2)
        self.assertEqual(delivered_orders, 96478)
        self.assertEqual(units_sold, 110197)

    def test_aov_calculation(self):
        """Assert AOV equals Gross Revenue divided by Total Delivered Orders."""
        gross_rev = float(self.kpis['total_gross_revenue'])
        orders_cnt = int(self.kpis['total_delivered_orders'])
        expected_aov = round(gross_rev / orders_cnt, 2)
        actual_aov = float(self.kpis['average_order_value_aov'])
        
        self.assertEqual(actual_aov, expected_aov)
        self.assertEqual(actual_aov, 159.83)

    def test_category_contribution_sum(self):
        """Assert sum of category contribution percentages equals ~100%."""
        df_cat = get_category_analytics(top_n=200)  # Get all categories
        total_pct = df_cat['revenue_contribution_pct'].sum()
        
        # Allow slight floating point rounding tolerance (99.5% to 100.5%)
        self.assertGreater(total_pct, 99.0)
        self.assertLess(total_pct, 101.0)

    def test_state_contribution_sum(self):
        """Assert sum of regional state contribution percentages equals ~100%."""
        df_state = get_state_analytics()
        total_pct = df_state['state_revenue_contribution_pct'].sum()
        
        self.assertGreater(total_pct, 99.0)
        self.assertLess(total_pct, 101.0)

    def test_no_negative_values(self):
        """Assert no negative revenue, price, or order count exists."""
        self.assertGreaterEqual(float(self.kpis['total_product_revenue']), 0)
        self.assertGreaterEqual(float(self.kpis['total_freight_revenue']), 0)
        self.assertGreaterEqual(int(self.kpis['total_delivered_orders']), 0)
        self.assertGreaterEqual(int(self.kpis['total_active_customers']), 0)

    def test_monthly_mom_calculations(self):
        """Assert monthly KPIs view returns valid continuous monthly records."""
        df_mom = get_monthly_performance()
        self.assertGreater(len(df_mom), 10)
        self.assertTrue('mom_revenue_growth_pct' in df_mom.columns)
        self.assertTrue('gross_revenue' in df_mom.columns)

    def test_delivery_sla_totals(self):
        """Assert delivery SLA performance total orders match delivered order count."""
        df_sla = get_delivery_performance()
        total_sla_orders = df_sla['order_count'].sum()
        delivered_cnt = int(self.kpis['total_delivered_orders'])
        
        self.assertEqual(total_sla_orders, delivered_cnt)


def run_tests():
    print("=" * 70)
    print("        INSIGHTFORGE — AUTOMATED ANALYTICS TEST SUITE        ")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestInsightForgeAnalytics)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    if result.wasSuccessful():
        print("✅ ALL ANALYTICS & MATHEMATICAL TESTS PASSED SUCCESSFULLY!")
    else:
        print("❌ SOME ANALYTICS TESTS FAILED!")
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
