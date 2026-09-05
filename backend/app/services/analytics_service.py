import sys
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.analytics import (
    get_summary_kpis,
    get_monthly_performance,
    get_category_analytics,
    get_state_analytics,
    get_seller_analytics,
    get_delivery_performance,
    get_payment_analytics
)

class AnalyticsService:

    @staticmethod
    def fetch_canonical_kpis() -> Dict[str, Any]:
        raw = get_summary_kpis()
        return {
            "product_revenue": float(raw["total_product_revenue"]),
            "freight_revenue": float(raw["total_freight_revenue"]),
            "gross_revenue": float(raw["total_gross_revenue"]),
            "delivered_orders": int(raw["total_delivered_orders"]),
            "active_customers": int(raw["total_active_customers"]),
            "units_sold": int(raw["total_units_sold"]),
            "aov": float(raw["average_order_value_aov"]),
            "csat": float(raw["average_csat_score"])
        }

    @staticmethod
    def fetch_revenue_trend() -> List[Dict[str, Any]]:
        df = get_monthly_performance()
        results = []
        for _, r in df.iterrows():
            results.append({
                "month": str(r["sales_month"]),
                "total_orders": int(r["total_orders"]),
                "total_items_sold": int(r["total_items_sold"]),
                "product_revenue": float(r["product_revenue"]),
                "freight_revenue": float(r["freight_revenue"]),
                "gross_revenue": float(r["gross_revenue"]),
                "aov": float(r["aov"]),
                "prev_month_revenue": float(r["prev_month_revenue"]) if not pd_isna(r["prev_month_revenue"]) else None,
                "mom_revenue_growth_pct": float(r["mom_revenue_growth_pct"]) if not pd_isna(r["mom_revenue_growth_pct"]) else None,
                "mom_order_growth_pct": float(r["mom_order_growth_pct"]) if not pd_isna(r["mom_order_growth_pct"]) else None,
                "mom_aov_growth_pct": float(r["mom_aov_growth_pct"]) if not pd_isna(r["mom_aov_growth_pct"]) else None,
            })
        return results

    @staticmethod
    def fetch_categories(limit: int = 10) -> List[Dict[str, Any]]:
        df = get_category_analytics(top_n=limit)
        results = []
        for _, r in df.iterrows():
            results.append({
                "category": str(r["category_name"]),
                "total_orders": int(r["total_orders"]),
                "units_sold": int(r["units_sold"]),
                "total_revenue": float(r["total_revenue"]),
                "avg_item_price": float(r["avg_item_price"]),
                "avg_review_score": float(r["avg_review_score"]) if not pd_isna(r["avg_review_score"]) else None,
                "revenue_share_percent": float(r["revenue_contribution_pct"])
            })
        return results

    @staticmethod
    def fetch_states() -> List[Dict[str, Any]]:
        df = get_state_analytics()
        results = []
        for _, r in df.iterrows():
            results.append({
                "state": str(r["customer_state"]),
                "active_customers": int(r["active_customers"]),
                "total_orders": int(r["total_orders"]),
                "total_product_revenue": float(r["total_product_revenue"]),
                "total_freight_revenue": float(r["total_freight_revenue"]),
                "total_gross_revenue": float(r["total_gross_revenue"]),
                "avg_freight_cost": float(r["avg_freight_cost"]),
                "revenue_share_percent": float(r["state_revenue_contribution_pct"])
            })
        return results

    @staticmethod
    def fetch_sellers(limit: int = 10) -> List[Dict[str, Any]]:
        df = get_seller_analytics(top_n=limit)
        results = []
        for _, r in df.iterrows():
            results.append({
                "seller_id": str(r["seller_id"]),
                "seller_city": str(r["seller_city"]),
                "seller_state": str(r["seller_state"]),
                "total_orders_fulfilled": int(r["total_orders_fulfilled"]),
                "units_sold": int(r["units_sold"]),
                "unique_products_offered": int(r["unique_products_offered"]),
                "total_sales_revenue": float(r["total_sales_revenue"]),
                "avg_seller_review_score": float(r["avg_seller_review_score"]) if not pd_isna(r["avg_seller_review_score"]) else None
            })
        return results

    @staticmethod
    def fetch_delivery_performance() -> List[Dict[str, Any]]:
        df = get_delivery_performance()
        results = []
        for _, r in df.iterrows():
            results.append({
                "delivery_status": str(r["delivery_status"]),
                "order_count": int(r["order_count"]),
                "percentage": float(r["pct_of_total"]),
                "avg_actual_delivery_days": float(r["avg_actual_delivery_days"]) if not pd_isna(r["avg_actual_delivery_days"]) else None,
                "avg_estimated_delivery_days": float(r["avg_estimated_delivery_days"]) if not pd_isna(r["avg_estimated_delivery_days"]) else None,
                "avg_delay_days": float(r["avg_delay_days"]) if not pd_isna(r["avg_delay_days"]) else None
            })
        return results

    @staticmethod
    def fetch_payments() -> List[Dict[str, Any]]:
        df = get_payment_analytics()
        results = []
        for _, r in df.iterrows():
            results.append({
                "payment_type": str(r["payment_type"]),
                "order_count": int(r["order_count"]),
                "total_payment_value": float(r["total_payment_value"]),
                "avg_payment_amount": float(r["avg_payment_amount"]),
                "avg_installments": float(r["avg_installments"])
            })
        return results


def pd_isna(val) -> bool:
    try:
        import pandas as pd
        return pd.isna(val)
    except Exception:
        return val is None
