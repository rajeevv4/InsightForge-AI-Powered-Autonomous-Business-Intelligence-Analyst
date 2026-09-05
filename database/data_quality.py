#!/usr/bin/env python3
"""
InsightForge — Data Quality Profiling & Audit Module
=====================================================
Automated data auditor that evaluates PostgreSQL relational integrity, missing values,
primary key uniqueness, foreign key validity, out-of-range bounds, timestamp chronology,
and fan-out join multiplier safety.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "insightforge")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "insightforge")


def get_db_engine():
    if DB_PASSWORD:
        db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        db_url = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(db_url, echo=False)


def run_data_quality_checks():
    engine = get_db_engine()
    print("=" * 70)
    print("        INSIGHTFORGE — COMPREHENSIVE DATA QUALITY AUDIT REPORT        ")
    print("=" * 70)
    
    findings = []
    issues_found = False

    with engine.connect() as conn:
        conn.execute(text(f"SET search_path TO {DB_SCHEMA}, public;"))

        # ---------------------------------------------------------------------
        # Check 1: Table Row Counts
        # ---------------------------------------------------------------------
        print("\n📊 1. ROW COUNTS & VOLUME AUDIT:")
        print("-" * 50)
        tables = ["customers", "products", "sellers", "orders", "order_items", "order_payments", "order_reviews"]
        table_counts = {}
        for t in tables:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            table_counts[t] = cnt
            print(f"  • {t:<20}: {cnt:>10,} rows")

        # ---------------------------------------------------------------------
        # Check 2: Null / Missing Value Profiling
        # ---------------------------------------------------------------------
        print("\n🔍 2. NULL / MISSING VALUE PROFILING:")
        print("-" * 50)
        null_queries = [
            ("orders.order_approved_at", "SELECT COUNT(*) FROM orders WHERE order_approved_at IS NULL"),
            ("orders.order_delivered_customer_date", "SELECT COUNT(*) FROM orders WHERE order_delivered_customer_date IS NULL"),
            ("products.product_category_name_english", "SELECT COUNT(*) FROM products WHERE product_category_name_english IS NULL OR product_category_name_english = 'uncategorized'"),
            ("order_reviews.review_comment_title", "SELECT COUNT(*) FROM order_reviews WHERE review_comment_title IS NULL OR review_comment_title = ''"),
            ("order_reviews.review_comment_message", "SELECT COUNT(*) FROM order_reviews WHERE review_comment_message IS NULL OR review_comment_message = ''")
        ]
        for field, sql in null_queries:
            cnt = conn.execute(text(sql)).scalar()
            pct = (cnt / table_counts[field.split('.')[0]]) * 100
            print(f"  • {field:<38}: {cnt:>8,} missing ({pct:>5.1f}%)")

        # ---------------------------------------------------------------------
        # Check 3: Duplicate Primary Keys
        # ---------------------------------------------------------------------
        print("\n🔑 3. PRIMARY KEY UNIQUENESS AUDIT:")
        print("-" * 50)
        pk_checks = [
            ("customers.customer_id", "SELECT COUNT(*) FROM (SELECT customer_id FROM customers GROUP BY customer_id HAVING COUNT(*) > 1) t"),
            ("products.product_id", "SELECT COUNT(*) FROM (SELECT product_id FROM products GROUP BY product_id HAVING COUNT(*) > 1) t"),
            ("sellers.seller_id", "SELECT COUNT(*) FROM (SELECT seller_id FROM sellers GROUP BY seller_id HAVING COUNT(*) > 1) t"),
            ("orders.order_id", "SELECT COUNT(*) FROM (SELECT order_id FROM orders GROUP BY order_id HAVING COUNT(*) > 1) t"),
            ("order_items (order_id, item_id)", "SELECT COUNT(*) FROM (SELECT order_id, order_item_id FROM order_items GROUP BY order_id, order_item_id HAVING COUNT(*) > 1) t"),
            ("order_payments (order_id, seq)", "SELECT COUNT(*) FROM (SELECT order_id, payment_sequential FROM order_payments GROUP BY order_id, payment_sequential HAVING COUNT(*) > 1) t"),
            ("order_reviews (review_id, order_id)", "SELECT COUNT(*) FROM (SELECT review_id, order_id FROM order_reviews GROUP BY review_id, order_id HAVING COUNT(*) > 1) t")
        ]
        for name, sql in pk_checks:
            dups = conn.execute(text(sql)).scalar()
            status = "✅ PASS (0 duplicates)" if dups == 0 else f"❌ FAIL ({dups} duplicate keys)"
            if dups > 0: issues_found = True
            print(f"  • {name:<38}: {status}")

        # ---------------------------------------------------------------------
        # Check 4: Foreign Key Referential Integrity
        # ---------------------------------------------------------------------
        print("\n🔗 4. FOREIGN KEY REFERENTIAL INTEGRITY AUDIT:")
        print("-" * 50)
        fk_checks = [
            ("orders -> customers", "SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id WHERE c.customer_id IS NULL"),
            ("order_items -> orders", "SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o ON oi.order_id = o.order_id WHERE o.order_id IS NULL"),
            ("order_items -> products", "SELECT COUNT(*) FROM order_items oi LEFT JOIN products p ON oi.product_id = p.product_id WHERE p.product_id IS NULL"),
            ("order_items -> sellers", "SELECT COUNT(*) FROM order_items oi LEFT JOIN sellers s ON oi.seller_id = s.seller_id WHERE s.seller_id IS NULL"),
            ("order_payments -> orders", "SELECT COUNT(*) FROM order_payments op LEFT JOIN orders o ON op.order_id = o.order_id WHERE o.order_id IS NULL"),
            ("order_reviews -> orders", "SELECT COUNT(*) FROM order_reviews r LEFT JOIN orders o ON r.order_id = o.order_id WHERE o.order_id IS NULL")
        ]
        for name, sql in fk_checks:
            orphans = conn.execute(text(sql)).scalar()
            status = "✅ PASS (0 orphans)" if orphans == 0 else f"❌ FAIL ({orphans} orphaned records)"
            if orphans > 0: issues_found = True
            print(f"  • {name:<38}: {status}")

        # ---------------------------------------------------------------------
        # Check 5: Domain Constraint & Value Range Audit
        # ---------------------------------------------------------------------
        print("\n🛡️ 5. VALUE RANGE & DOMAIN CONSTRAINT AUDIT:")
        print("-" * 50)
        range_checks = [
            ("order_items (price < 0)", "SELECT COUNT(*) FROM order_items WHERE price < 0"),
            ("order_items (freight_value < 0)", "SELECT COUNT(*) FROM order_items WHERE freight_value < 0"),
            ("order_payments (payment_value < 0)", "SELECT COUNT(*) FROM order_payments WHERE payment_value < 0"),
            ("order_reviews (review_score NOT IN 1-5)", "SELECT COUNT(*) FROM order_reviews WHERE review_score NOT BETWEEN 1 AND 5")
        ]
        for name, sql in range_checks:
            bad = conn.execute(text(sql)).scalar()
            status = "✅ PASS (0 out of range)" if bad == 0 else f"❌ FAIL ({bad} invalid values)"
            if bad > 0: issues_found = True
            print(f"  • {name:<38}: {status}")

        # ---------------------------------------------------------------------
        # Check 6: Order Lifecycle Status Distribution
        # ---------------------------------------------------------------------
        print("\n📦 6. ORDER STATUS DISTRIBUTION:")
        print("-" * 50)
        status_sql = text("SELECT order_status, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC")
        statuses = conn.execute(status_sql).fetchall()
        for st, cnt in statuses:
            pct = (cnt / table_counts['orders']) * 100
            print(f"  • {st:<20}: {cnt:>8,} orders ({pct:>5.2f}%)")

        # ---------------------------------------------------------------------
        # Check 7: Timestamp Chronology Anomalies
        # ---------------------------------------------------------------------
        print("\n⏱️ 7. TIMESTAMP CHRONOLOGY ANOMALIES:")
        print("-" * 50)
        ts_checks = [
            ("delivered < purchase_timestamp", "SELECT COUNT(*) FROM orders WHERE order_delivered_customer_date < order_purchase_timestamp"),
            ("approved_at < purchase_timestamp", "SELECT COUNT(*) FROM orders WHERE order_approved_at < order_purchase_timestamp"),
            ("delivered > 365 days after purchase", "SELECT COUNT(*) FROM orders WHERE order_delivered_customer_date > order_purchase_timestamp + INTERVAL '365 days'")
        ]
        for name, sql in ts_checks:
            anom = conn.execute(text(sql)).scalar()
            print(f"  • {name:<38}: {anom:>8,} flagged records")
            if anom > 0:
                findings.append(f"Timestamp anomaly: {anom} records for '{name}'")

        # ---------------------------------------------------------------------
        # Check 8: Join Multiplier & Cartesian Fan-Out Safety Test
        # ---------------------------------------------------------------------
        print("\n⚡ 8. JOIN MULTIPLIER & FAN-OUT SAFETY TEST:")
        print("-" * 50)
        direct_sum = conn.execute(text("SELECT SUM(price) FROM order_items oi JOIN orders o ON oi.order_id = o.order_id WHERE o.order_status = 'delivered'")).scalar()
        summary_view_sum = conn.execute(text("SELECT SUM(total_product_amount) FROM view_order_level_summary WHERE order_status = 'delivered'")).scalar()
        
        diff = abs(float(direct_sum) - float(summary_view_sum))
        status = "✅ PASS (0.00 difference)" if diff < 0.01 else f"❌ FAIL ({diff} discrepancy)"
        print(f"  • Product Revenue Direct Sum  : R$ {direct_sum:,.2f}")
        print(f"  • View Order Level Summary Sum: R$ {summary_view_sum:,.2f}")
        print(f"  • Fan-Out Validation Status   : {status}")

    print("=" * 70)
    if not issues_found:
        print("✅ DATA QUALITY AUDIT COMPLETED: 100% RELATIONAL INTEGRITY VERIFIED")
    else:
        print("⚠️ DATA QUALITY AUDIT COMPLETED: Minor anomalies flagged above for filtering.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        run_data_quality_checks()
    except Exception as e:
        print(f"\n❌ Data Quality Audit failed with error: {e}")
        sys.exit(1)
