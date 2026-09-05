#!/usr/bin/env python3
"""
InsightForge — Semantic Layer PyUnit Test Suite
================================================
Automated test suite asserting semantic layer file completeness, YAML syntax integrity,
metric formulas, cross-table schema references, and fan-out join documentation.
"""

import sys
import unittest
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SEMANTIC_DIR = BASE_DIR / "semantic"

sys.path.insert(0, str(BASE_DIR))
from semantic.validate_semantic_layer import validate_semantic_layer, load_yaml, VALID_SCHEMA_TABLES


class TestInsightForgeSemanticLayer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.glossary = load_yaml(SEMANTIC_DIR / "business_glossary.yaml")
        cls.metrics = load_yaml(SEMANTIC_DIR / "metrics.yaml")
        cls.dimensions = load_yaml(SEMANTIC_DIR / "dimensions.yaml")
        cls.relationships = load_yaml(SEMANTIC_DIR / "relationships.yaml")

    def test_files_load_successfully(self):
        """Assert all semantic YAML files load without syntax errors."""
        self.assertIsNotNone(self.glossary)
        self.assertIsNotNone(self.metrics)
        self.assertIsNotNone(self.dimensions)
        self.assertIsNotNone(self.relationships)

    def test_required_kpis_exist(self):
        """Assert all canonical core metrics exist in metrics.yaml."""
        required_metrics = [
            "gross_revenue", "product_revenue", "freight_revenue",
            "delivered_orders", "active_customers", "units_sold",
            "aov", "csat"
        ]
        for m in required_metrics:
            self.assertIn(m, self.metrics, f"Metric '{m}' missing from metrics.yaml")

    def test_canonical_metric_values(self):
        """Assert canonical benchmark values in metrics.yaml match verified database values."""
        self.assertEqual(self.metrics["product_revenue"]["canonical_value"], 13221498.11)
        self.assertEqual(self.metrics["freight_revenue"]["canonical_value"], 2198275.64)
        self.assertEqual(self.metrics["gross_revenue"]["canonical_value"], 15419773.75)
        self.assertEqual(self.metrics["delivered_orders"]["canonical_value"], 96478)
        self.assertEqual(self.metrics["active_customers"]["canonical_value"], 93358)
        self.assertEqual(self.metrics["units_sold"]["canonical_value"], 110197)
        self.assertEqual(self.metrics["aov"]["canonical_value"], 159.83)
        self.assertEqual(self.metrics["csat"]["canonical_value"], 4.16)

    def test_required_glossary_terms_exist(self):
        """Assert required business terms exist in business_glossary.yaml."""
        required_terms = [
            "revenue", "product_revenue", "freight_revenue", "gross_revenue",
            "delivered_orders", "active_customers", "units_sold", "average_order_value",
            "customer_satisfaction", "on_time_delivery", "delayed_delivery",
            "undelivered_orders", "revenue_share", "order", "customer", "product",
            "seller", "payment_method", "review_score"
        ]
        for term in required_terms:
            self.assertIn(term, self.glossary, f"Glossary term '{term}' missing from business_glossary.yaml")

    def test_required_dimensions_exist(self):
        """Assert required analytical dimensions exist in dimensions.yaml."""
        required_dims = [
            "date", "month", "product_category", "customer_state",
            "seller", "payment_type", "order_status", "review_score", "delivery_status"
        ]
        for d in required_dims:
            self.assertIn(d, self.dimensions, f"Dimension '{d}' missing from dimensions.yaml")

    def test_no_duplicate_display_names(self):
        """Assert no duplicate metric or glossary names exist."""
        metric_names = [m["metric_name"] for m in self.metrics.values()]
        self.assertEqual(len(metric_names), len(set(metric_names)), "Duplicate metric display names detected")

        glossary_names = [g["name"] for g in self.glossary.values()]
        self.assertEqual(len(glossary_names), len(set(glossary_names)), "Duplicate glossary display names detected")

    def test_referenced_tables_and_columns_valid(self):
        """Assert all referenced schema objects match real database tables/columns."""
        for dim_name, dim_info in self.dimensions.items():
            tbl = dim_info["source_table"]
            col = dim_info["source_column"]
            self.assertIn(tbl, VALID_SCHEMA_TABLES, f"Dimension '{dim_name}' references unknown table '{tbl}'")
            self.assertIn(col, VALID_SCHEMA_TABLES[tbl], f"Dimension '{dim_name}' references unknown column '{col}'")

    def test_fan_out_rules_documented(self):
        """Assert fan-out multiplication warning and safe design patterns are documented."""
        fan_out = self.relationships.get("fan_out_rules", {})
        self.assertIn("critical_warning", fan_out)
        self.assertIn("historical_incident", fan_out)
        self.assertIn("safe_design_patterns", fan_out)

    def test_full_validator_runs_cleanly(self):
        """Assert full validate_semantic_layer() script returns True."""
        result = validate_semantic_layer()
        self.assertTrue(result, "validate_semantic_layer() reported errors")


def run_tests():
    print("=" * 70)
    print("        INSIGHTFORGE — SEMANTIC LAYER TEST SUITE        ")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestInsightForgeSemanticLayer)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
