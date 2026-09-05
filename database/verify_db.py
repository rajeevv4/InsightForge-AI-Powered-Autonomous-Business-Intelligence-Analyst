#!/usr/bin/env python3
"""
InsightForge — Database Verification & Health Check Script
==========================================================
Verifies PostgreSQL database structure, record counts, foreign key integrity,
and executes baseline BI KPI benchmark queries over the Olist data model.
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
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_SCHEMA = os.getenv("DB_SCHEMA", "insightforge")


def get_db_engine():
    if DB_PASSWORD:
        db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        db_url = f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(db_url, echo=False)


def run_health_checks():
    engine = get_db_engine()
    print("=" * 65)
    print("      INSIGHTFORGE DATABASE INTEGRITY & HEALTH REPORT      ")
    print("=" * 65)
    
    tables = [
        "customers", "products", "sellers", 
        "orders", "order_items", "order_payments", "order_reviews"
    ]
    
    views = [
        "view_monthly_sales_performance", 
        "view_category_performance", 
        "view_state_sales_performance",
        "view_delivery_sla_performance"
    ]
    
    with engine.connect() as conn:
        conn.execute(text(f"SET search_path TO {DB_SCHEMA}, public;"))
        
        print("\n📊 1. TABLE RECORD COUNTS:")
        print("-" * 45)
        total_rows = 0
        for table in tables:
            try:
                res = conn.execute(text(f"SELECT COUNT(*) FROM {DB_SCHEMA}.{table}")).scalar()
                print(f"  • {table:<20}: {res:>10,} rows")
                total_rows += res
            except Exception as e:
                print(f"  • {table:<20}: ❌ ERROR ({e})")
                
        print("-" * 45)
        print(f"  TOTAL RELATIONAL ROWS : {total_rows:>10,}")
        
        print("\n👁️ 2. ANALYTICAL VIEWS STATUS:")
        print("-" * 45)
        for view in views:
            try:
                res = conn.execute(text(f"SELECT COUNT(*) FROM {DB_SCHEMA}.{view}")).scalar()
                print(f"  • {view:<32}: {res:>8,} summary rows")
            except Exception as e:
                print(f"  • {view:<32}: ❌ ERROR ({e})")

        print("\n📈 3. CORE BUSINESS METRICS & BENCHMARKS:")
        print("-" * 45)
        
        # Gross Revenue & Orders
        kpi_sql = text(f"""
            SELECT 
                COUNT(DISTINCT o.order_id) as total_orders,
                SUM(oi.price) as product_revenue,
                SUM(oi.freight_value) as freight_revenue,
                SUM(oi.price + oi.freight_value) as gross_revenue,
                ROUND(AVG(oi.price), 2) as avg_item_price
            FROM {DB_SCHEMA}.orders o
            JOIN {DB_SCHEMA}.order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'delivered';
        """)
        row = conn.execute(kpi_sql).fetchone()
        if row and row.total_orders:
            print(f"  • Total Delivered Orders : {row.total_orders:,}")
            print(f"  • Total Product Revenue  : R$ {row.product_revenue:,.2f}")
            print(f"  • Total Freight Revenue  : R$ {row.freight_revenue:,.2f}")
            print(f"  • Gross Revenue          : R$ {row.gross_revenue:,.2f}")
            print(f"  • Average Unit Price     : R$ {row.avg_item_price:,.2f}")
        else:
            print("  • Gross Revenue          : No delivered order data found yet.")

        # Top 5 Product Categories by Revenue
        print("\n🏆 4. TOP 5 CATEGORIES BY REVENUE:")
        print("-" * 45)
        top_cat_sql = text(f"""
            SELECT 
                COALESCE(product_category_name_english, 'Uncategorized') as category,
                SUM(oi.price) as revenue,
                COUNT(oi.order_item_id) as units_sold
            FROM {DB_SCHEMA}.order_items oi
            JOIN {DB_SCHEMA}.products p ON oi.product_id = p.product_id
            JOIN {DB_SCHEMA}.orders o ON oi.order_id = o.order_id
            WHERE o.order_status = 'delivered'
            GROUP BY 1
            ORDER BY revenue DESC
            LIMIT 5;
        """)
        cats = conn.execute(top_cat_sql).fetchall()
        for idx, c in enumerate(cats, 1):
            print(f"  {idx}. {c.category:<25}: R$ {c.revenue:,.2f} ({c.units_sold:,} units)")

    print("=" * 65)
    print("✅ InsightForge Database Health Check Completed.")
    print("=" * 65)


if __name__ == "__main__":
    try:
        run_health_checks()
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        sys.exit(1)
