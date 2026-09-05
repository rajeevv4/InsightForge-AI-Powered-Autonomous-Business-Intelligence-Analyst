#!/usr/bin/env python3
"""
InsightForge — Semantic Layer Validator
=======================================
Automated verification script checking YAML semantic specifications against:
  - Required business terms, metric keys, dimensions, and relationships
  - Database schema table and column existence (schema.sql & views.sql)
  - Duplicate key detection and referential integrity
"""

import sys
import yaml
from pathlib import Path

# Paths
SEMANTIC_DIR = Path(__file__).resolve().parent

# Project Schema & Views Definition Registry (Authoritative map of valid project tables & columns)
VALID_SCHEMA_TABLES = {
    "customers": {
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state"
    },
    "products": {
        "product_id", "product_category_name", "product_category_name_english",
        "product_name_length", "product_description_length", "product_photos_qty",
        "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
    },
    "sellers": {
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"
    },
    "orders": {
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date"
    },
    "order_items": {
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value"
    },
    "order_payments": {
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value"
    },
    "order_reviews": {
        "review_id", "order_id", "review_score", "review_comment_title",
        "review_comment_message", "review_creation_date", "review_answer_timestamp"
    },
    # Analytical Views
    "view_order_level_summary": {
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
        "item_count", "total_product_amount", "total_freight_amount", "gross_order_amount"
    },
    "view_monthly_kpis_mom": {
        "sales_month", "total_orders", "total_items_sold", "product_revenue",
        "freight_revenue", "gross_revenue", "aov", "prev_month_revenue",
        "mom_revenue_growth_pct", "prev_month_orders", "mom_order_growth_pct",
        "prev_month_aov", "mom_aov_growth_pct"
    },
    "view_category_contribution": {
        "category_name", "total_orders", "units_sold", "total_revenue",
        "avg_item_price", "avg_review_score", "revenue_contribution_pct"
    },
    "view_state_contribution": {
        "customer_state", "active_customers", "total_orders", "total_product_revenue",
        "total_freight_revenue", "total_gross_revenue", "avg_freight_cost",
        "state_revenue_contribution_pct"
    },
    "view_delivery_sla_performance": {
        "order_id", "customer_id", "order_purchase_timestamp",
        "order_delivered_customer_date", "order_estimated_delivery_date",
        "actual_delivery_days", "estimated_delivery_days", "delivery_status", "delay_days"
    },
    "view_seller_performance": {
        "seller_id", "seller_city", "seller_state", "total_orders_fulfilled",
        "units_sold", "unique_products_offered", "total_sales_revenue", "avg_seller_review_score"
    }
}

# Requirements
REQUIRED_GLOSSARY_TERMS = {
    "revenue", "product_revenue", "freight_revenue", "gross_revenue",
    "delivered_orders", "active_customers", "units_sold", "average_order_value",
    "customer_satisfaction", "on_time_delivery", "delayed_delivery",
    "undelivered_orders", "revenue_share", "order", "customer", "product",
    "seller", "payment_method", "review_score"
}

REQUIRED_METRICS = {
    "gross_revenue", "product_revenue", "freight_revenue", "delivered_orders",
    "active_customers", "units_sold", "aov", "csat"
}

REQUIRED_DIMENSIONS = {
    "date", "month", "product_category", "customer_state", "seller",
    "payment_type", "order_status", "review_score", "delivery_status"
}


def load_yaml(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"Missing required semantic file: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_semantic_layer():
    print("=" * 70)
    print("        INSIGHTFORGE — SEMANTIC LAYER VALIDATION SUITE        ")
    print("=" * 70)

    errors = []
    warnings = []

    # 1. Load Files
    try:
        glossary = load_yaml(SEMANTIC_DIR / "business_glossary.yaml")
        metrics = load_yaml(SEMANTIC_DIR / "metrics.yaml")
        dimensions = load_yaml(SEMANTIC_DIR / "dimensions.yaml")
        rel_data = load_yaml(SEMANTIC_DIR / "relationships.yaml")
    except Exception as e:
        print(f"❌ YAML Loading Error: {e}")
        return False

    print("✅ All YAML semantic specification files parsed successfully.")

    # 2. Validate Business Glossary
    print("\n🔍 Validating Business Glossary...")
    glossary_keys = set(glossary.keys()) if glossary else set()
    missing_terms = REQUIRED_GLOSSARY_TERMS - glossary_keys
    if missing_terms:
        errors.append(f"Glossary missing required terms: {sorted(list(missing_terms))}")
    else:
        print(f"  • Glossary terms count: {len(glossary_keys)} (All required terms present)")

    # Check duplicate names in glossary
    glossary_names = []
    for key, info in (glossary or {}).items():
        name = info.get("name")
        if not name:
            errors.append(f"Glossary term '{key}' is missing 'name' field.")
        elif name in glossary_names:
            errors.append(f"Duplicate glossary display name found: '{name}'")
        else:
            glossary_names.append(name)

        # Check tables & columns in source
        source = info.get("source", {})
        for tbl in source.get("tables", []):
            if tbl not in VALID_SCHEMA_TABLES:
                errors.append(f"Glossary term '{key}' references unknown table '{tbl}'")
        for col_ref in source.get("columns", []):
            if "." in col_ref:
                tbl, col = col_ref.split(".", 1)
                if tbl in VALID_SCHEMA_TABLES and col not in VALID_SCHEMA_TABLES[tbl]:
                    errors.append(f"Glossary term '{key}' references unknown column '{col}' in table '{tbl}'")

    # 3. Validate Metric Definitions
    print("\n🔍 Validating Metric Definitions...")
    metric_keys = set(metrics.keys()) if metrics else set()
    missing_metrics = REQUIRED_METRICS - metric_keys
    if missing_metrics:
        errors.append(f"Metrics missing required keys: {sorted(list(missing_metrics))}")
    else:
        print(f"  • Metric definitions count: {len(metric_keys)} (All required metrics present)")

    metric_names = []
    for m_key, m_info in (metrics or {}).items():
        m_name = m_info.get("metric_name")
        if not m_name:
            errors.append(f"Metric '{m_key}' is missing 'metric_name' field.")
        elif m_name in metric_names:
            errors.append(f"Duplicate metric display name found: '{m_name}'")
        else:
            metric_names.append(m_name)

        # Check required metric schema fields
        req_fields = ["description", "formula", "source_tables", "source_columns", "filters", "grain", "unit", "aggregation"]
        for rf in req_fields:
            if rf not in m_info:
                errors.append(f"Metric '{m_key}' missing required field '{rf}'")

        # Validate source tables and columns
        for tbl in m_info.get("source_tables", []):
            if tbl not in VALID_SCHEMA_TABLES:
                errors.append(f"Metric '{m_key}' references unknown source table '{tbl}'")
        for col_ref in m_info.get("source_columns", []):
            if "." in col_ref:
                tbl, col = col_ref.split(".", 1)
                if tbl in VALID_SCHEMA_TABLES and col not in VALID_SCHEMA_TABLES[tbl]:
                    errors.append(f"Metric '{m_key}' references unknown column '{col}' in table '{tbl}'")

    # 4. Validate Dimensions
    print("\n🔍 Validating Dimensions...")
    dim_keys = set(dimensions.keys()) if dimensions else set()
    missing_dims = REQUIRED_DIMENSIONS - dim_keys
    if missing_dims:
        errors.append(f"Dimensions missing required keys: {sorted(list(missing_dims))}")
    else:
        print(f"  • Analytical dimensions count: {len(dim_keys)} (All required dimensions present)")

    for d_key, d_info in (dimensions or {}).items():
        tbl = d_info.get("source_table")
        col = d_info.get("source_column")
        if not tbl or tbl not in VALID_SCHEMA_TABLES:
            errors.append(f"Dimension '{d_key}' references invalid source_table '{tbl}'")
        elif col and col not in VALID_SCHEMA_TABLES[tbl]:
            errors.append(f"Dimension '{d_key}' references invalid source_column '{col}' in table '{tbl}'")

    # 5. Validate Relationships
    print("\n🔍 Validating Relationships...")
    relationships = rel_data.get("relationships", []) if rel_data else []
    print(f"  • Relationships count: {len(relationships)}")

    for rel in relationships:
        parent = rel.get("parent_table")
        child = rel.get("child_table")
        key = rel.get("join_key")

        if parent not in VALID_SCHEMA_TABLES:
            errors.append(f"Relationship parent table '{parent}' does not exist in schema")
        if child not in VALID_SCHEMA_TABLES:
            errors.append(f"Relationship child table '{child}' does not exist in schema")

        if parent in VALID_SCHEMA_TABLES and key and key not in VALID_SCHEMA_TABLES[parent]:
            errors.append(f"Relationship key '{key}' not found in parent table '{parent}'")
        if child in VALID_SCHEMA_TABLES and key and key not in VALID_SCHEMA_TABLES[child]:
            errors.append(f"Relationship key '{key}' not found in child table '{child}'")

    # Check fan out documentation rules
    fan_out = rel_data.get("fan_out_rules", {}) if rel_data else {}
    if not fan_out.get("critical_warning"):
        warnings.append("Relationships file missing fan_out_rules.critical_warning section.")

    # 6. Report Summary
    print("\n" + "=" * 70)
    if warnings:
        print("⚠️ WARNINGS:")
        for w in warnings:
            print(f"  • {w}")

    if errors:
        print("❌ VALIDATION FAILED WITH ERRORS:")
        for e in errors:
            print(f"  • {e}")
        print("=" * 70)
        return False
    else:
        print("✅ SEMANTIC LAYER VALIDATION SUCCESSFUL!")
        print(f"  • Glossary terms validated : {len(glossary_keys)}")
        print(f"  • Metrics validated        : {len(metric_keys)}")
        print(f"  • Dimensions validated     : {len(dim_keys)}")
        print(f"  • Relationships validated  : {len(relationships)}")
        print("=" * 70)
        return True


if __name__ == "__main__":
    success = validate_semantic_layer()
    if not success:
        sys.exit(1)
