import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.app.schemas.analytics import (
    MonthlyTrendItem,
    CategoryItem,
    StateItem,
    SellerItem,
    DeliverySLAItem,
    PaymentItem
)
from backend.app.services.analytics_service import AnalyticsService
from backend.app.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/revenue-trend", response_model=List[MonthlyTrendItem])
def get_revenue_trend():
    try:
        return AnalyticsService.fetch_revenue_trend()
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /revenue-trend: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch revenue trend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch revenue trend data. Please try again later.")

@router.get("/categories", response_model=List[CategoryItem])
def get_categories(limit: Optional[int] = Query(default=10, ge=1, le=500)):
    try:
        return AnalyticsService.fetch_categories(limit=limit)
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /categories: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch category analytics. Please try again later.")

@router.get("/states", response_model=List[StateItem])
def get_states():
    try:
        return AnalyticsService.fetch_states()
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /states: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch state analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch state analytics. Please try again later.")

@router.get("/sellers", response_model=List[SellerItem])
def get_sellers(limit: Optional[int] = Query(default=10, ge=1, le=500)):
    try:
        return AnalyticsService.fetch_sellers(limit=limit)
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /sellers: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch sellers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch seller analytics. Please try again later.")

@router.get("/delivery", response_model=List[DeliverySLAItem])
def get_delivery():
    try:
        return AnalyticsService.fetch_delivery_performance()
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /delivery: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch delivery analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch delivery analytics. Please try again later.")

@router.get("/payments", response_model=List[PaymentItem])
def get_payments():
    try:
        return AnalyticsService.fetch_payments()
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /payments: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch payment analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch payment analytics. Please try again later.")
