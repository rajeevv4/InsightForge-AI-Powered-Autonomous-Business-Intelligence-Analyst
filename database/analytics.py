#!/usr/bin/env python3
"""
InsightForge — Business Analytics & Comparison Engine
=====================================================
Centralized analytical engine providing Python & SQL analytical functions for:
  - Core Business KPIs (Revenue, AOV, Orders, Customers, CSAT)
  - Monthly Trend Analysis & Month-over-Month (MoM) Growth Rates
  - Category Revenue, Units Sold & Category Contribution %
  - Regional Customer State Revenue & Regional Contribution %
  - Merchant / Seller Performance Analysis
  - Delivery SLA & Fulfillment Delay Analysis
  - Payment Method Breakdown
"""

import os
import sys
import pandas as pd
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


def get_summary_kpis():
    """Retrieve overall company executive summary metrics for delivered orders."""
    engine = get_db_engine()
    sql = text(f"""
        WITH sales AS (
            SELECT 
                COUNT(DISTINCT o.order_id) AS total_delivered_orders,
                COUNT(DISTINCT c.customer_unique_id) AS total_active_customers,
                COUNT(oi.order_item_id) AS total_units_sold,
                SUM(oi.price) AS total_product_revenue,
                SUM(oi.freight_value) AS total_freight_revenue,
                SUM(oi.price + oi.freight_value) AS total_gross_revenue,
                ROUND(SUM(oi.price + oi.freight_value) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS average_order_value_aov,
                ROUND(AVG(oi.price), 2) AS average_item_price
            FROM {DB_SCHEMA}.orders o
            JOIN {DB_SCHEMA}.customers c ON o.customer_id = c.customer_id
            JOIN {DB_SCHEMA}.order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'delivered'
        ),
        reviews AS (
            SELECT ROUND(AVG(r.review_score), 2) AS average_csat_score
            FROM {DB_SCHEMA}.order_reviews r
            JOIN {DB_SCHEMA}.orders o ON r.order_id = o.order_id
            WHERE o.order_status = 'delivered'
        )
        SELECT s.*, r.average_csat_score
        FROM sales s, reviews r;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df.to_dict(orient="records")[0]


def get_monthly_performance():
    """Retrieve monthly sales performance with Month-over-Month (MoM) growth rates."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            sales_month,
            total_orders,
            total_items_sold,
            product_revenue,
            freight_revenue,
            gross_revenue,
            aov,
            prev_month_revenue,
            mom_revenue_growth_pct,
            prev_month_orders,
            mom_order_growth_pct,
            mom_aov_growth_pct
        FROM {DB_SCHEMA}.view_monthly_kpis_mom
        ORDER BY sales_month ASC;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_category_analytics(top_n=10):
    """Retrieve top performing product categories with revenue contribution %."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            category_name,
            total_orders,
            units_sold,
            total_revenue,
            avg_item_price,
            avg_review_score,
            revenue_contribution_pct
        FROM {DB_SCHEMA}.view_category_contribution
        ORDER BY total_revenue DESC
        LIMIT {top_n};
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_bottom_categories(limit=5):
    """Retrieve lowest performing product categories by revenue."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            category_name,
            total_orders,
            units_sold,
            total_revenue,
            avg_item_price,
            avg_review_score,
            revenue_contribution_pct
        FROM {DB_SCHEMA}.view_category_contribution
        WHERE total_revenue > 0
        ORDER BY total_revenue ASC
        LIMIT {limit};
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_state_analytics():
    """Retrieve regional customer state sales performance & state revenue contribution %."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            customer_state,
            active_customers,
            total_orders,
            total_product_revenue,
            total_freight_revenue,
            total_gross_revenue,
            avg_freight_cost,
            state_revenue_contribution_pct
        FROM {DB_SCHEMA}.view_state_contribution
        ORDER BY total_gross_revenue DESC;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_seller_analytics(top_n=10):
    """Retrieve top merchants/sellers by sales revenue."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            seller_id,
            seller_city,
            seller_state,
            total_orders_fulfilled,
            units_sold,
            unique_products_offered,
            total_sales_revenue,
            avg_seller_review_score
        FROM {DB_SCHEMA}.view_seller_performance
        ORDER BY total_sales_revenue DESC
        LIMIT {top_n};
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_delivery_performance():
    """Retrieve overall delivery SLA & fulfillment performance statistics."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            delivery_status,
            COUNT(*) AS order_count,
            ROUND(COUNT(*)::NUMERIC / (SELECT COUNT(*) FROM {DB_SCHEMA}.view_delivery_sla_performance) * 100, 2) AS pct_of_total,
            ROUND(AVG(actual_delivery_days), 2) AS avg_actual_delivery_days,
            ROUND(AVG(estimated_delivery_days), 2) AS avg_estimated_delivery_days,
            ROUND(AVG(delay_days), 2) AS avg_delay_days
        FROM {DB_SCHEMA}.view_delivery_sla_performance
        GROUP BY delivery_status
        ORDER BY order_count DESC;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def get_payment_analytics():
    """Retrieve payment method breakdown and installment statistics."""
    engine = get_db_engine()
    sql = text(f"""
        SELECT 
            op.payment_type,
            COUNT(DISTINCT op.order_id) AS order_count,
            SUM(op.payment_value) AS total_payment_value,
            ROUND(AVG(op.payment_value), 2) AS avg_payment_amount,
            ROUND(AVG(op.payment_installments), 1) AS avg_installments
        FROM {DB_SCHEMA}.order_payments op
        JOIN {DB_SCHEMA}.orders o ON op.order_id = o.order_id
        WHERE o.order_status = 'delivered'
        GROUP BY op.payment_type
        ORDER BY total_payment_value DESC;
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return df


def main():
    print("=" * 70)
    print("         INSIGHTFORGE — EXECUTIVE BUSINESS ANALYTICS REPORT        ")
    print("=" * 70)
    
    # 1. Executive Summary
    kpis = get_summary_kpis()
    print("\n📌 1. EXECUTIVE SUMMARY KPIs:")
    print("-" * 50)
    print(f"  • Gross Revenue (Inc. Freight) : R$ {kpis['total_gross_revenue']:,.2f}")
    print(f"  • Product Revenue             : R$ {kpis['total_product_revenue']:,.2f}")
    print(f"  • Freight Revenue             : R$ {kpis['total_freight_revenue']:,.2f}")
    print(f"  • Delivered Orders            : {kpis['total_delivered_orders']:,}")
    print(f"  • Active Customers            : {kpis['total_active_customers']:,}")
    print(f"  • Units Sold                  : {kpis['total_units_sold']:,}")
    print(f"  • Average Order Value (AOV)   : R$ {kpis['average_order_value_aov']:,.2f}")
    print(f"  • Customer Rating (CSAT)      : {kpis['average_csat_score']:.2f} / 5.0")

    # 2. Top Product Categories
    top_cats = get_category_analytics(5)
    print("\n🏆 2. TOP 5 PRODUCT CATEGORIES BY REVENUE:")
    print("-" * 50)
    for idx, row in top_cats.iterrows():
        print(f"  {idx+1}. {row['category_name']:<25}: R$ {row['total_revenue']:>12,.2f} ({row['revenue_contribution_pct']:>5.2f}% Share, CSAT: {row['avg_review_score']})")

    # 3. Regional Top States
    states = get_state_analytics().head(5)
    print("\n🗺️ 3. TOP 5 STATES BY REVENUE:")
    print("-" * 50)
    for idx, row in states.iterrows():
        print(f"  {idx+1}. {row['customer_state']:<5} (Customers: {row['active_customers']:>6,}): R$ {row['total_gross_revenue']:>12,.2f} ({row['state_revenue_contribution_pct']:>5.2f}% Share)")

    # 4. Delivery SLA Status
    sla = get_delivery_performance()
    print("\n🚚 4. DELIVERY FULFILLMENT SLA:")
    print("-" * 50)
    for idx, row in sla.iterrows():
        print(f"  • {row['delivery_status']:<12}: {row['order_count']:>6,} orders ({row['pct_of_total']:>5.2f}%, Avg Days: {row['avg_actual_delivery_days']})")

    # 5. Payment Breakdown
    payments = get_payment_analytics()
    print("\n💳 5. PAYMENT TYPE BREAKDOWN:")
    print("-" * 50)
    for idx, row in payments.iterrows():
        print(f"  • {row['payment_type']:<15}: R$ {row['total_payment_value']:>12,.2f} ({row['order_count']:>6,} orders, Avg Installments: {row['avg_installments']})")

    print("=" * 70)


if __name__ == "__main__":
    main()
