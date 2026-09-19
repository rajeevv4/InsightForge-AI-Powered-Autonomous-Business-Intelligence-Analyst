import sys
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.data_quality_service import DataQualityService


SUPPORTED_INTENTS: List[str] = [
    "kpi_summary",
    "revenue_trend",
    "category_analysis",
    "state_analysis",
    "seller_analysis",
    "payment_analysis",
    "delivery_analysis",
    "data_quality"
]


class AIAnalyticsRouter:
    """
    Controlled router mapping allow-listed AI intents to trusted, pre-validated
    analytics functions. NEVER executes arbitrary SQL or arbitrary user input.
    """

    @staticmethod
    def route_intent(intent: str) -> Dict[str, Any]:
        """
        Executes the analytics function corresponding to the validated intent
        and returns a standardized evidence dictionary.
        """
        if intent not in SUPPORTED_INTENTS:
            raise ValueError(f"Unsupported intent: '{intent}'. Must be one of {SUPPORTED_INTENTS}")

        if intent == "kpi_summary":
            data = AnalyticsService.fetch_canonical_kpis()
            metric = "Executive KPI Summary"
        elif intent == "revenue_trend":
            data = AnalyticsService.fetch_revenue_trend()
            metric = "Monthly Revenue & Order Performance Trend"
        elif intent == "category_analysis":
            data = AnalyticsService.fetch_categories(limit=10)
            metric = "Product Category Performance & Revenue Share"
        elif intent == "state_analysis":
            data = AnalyticsService.fetch_states()
            metric = "State-level Sales & Revenue Distribution"
        elif intent == "seller_analysis":
            data = AnalyticsService.fetch_sellers(limit=10)
            metric = "Seller Fulfillment & Revenue Performance"
        elif intent == "payment_analysis":
            data = AnalyticsService.fetch_payments()
            metric = "Payment Methods & Installment Distribution"
        elif intent == "delivery_analysis":
            data = AnalyticsService.fetch_delivery_performance()
            metric = "Delivery SLA & Logistics Performance"
        elif intent == "data_quality":
            data = DataQualityService.fetch_audit_summary()
            metric = "Data Quality Audit & Integrity Report"
        else:
            raise ValueError(f"Unhandled intent routing: {intent}")

        return {
            "source": "PostgreSQL analytics",
            "intent": intent,
            "metric": metric,
            "data": data
        }
