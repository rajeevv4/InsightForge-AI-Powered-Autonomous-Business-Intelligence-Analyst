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

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/revenue-trend", response_model=List[MonthlyTrendItem])
def get_revenue_trend():
    try:
        return AnalyticsService.fetch_revenue_trend()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch revenue trend: {str(e)}")

@router.get("/categories", response_model=List[CategoryItem])
def get_categories(limit: Optional[int] = Query(default=10, ge=1, le=100)):
    try:
        return AnalyticsService.fetch_categories(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")

@router.get("/states", response_model=List[StateItem])
def get_states():
    try:
        return AnalyticsService.fetch_states()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch state analytics: {str(e)}")

@router.get("/sellers", response_model=List[SellerItem])
def get_sellers(limit: Optional[int] = Query(default=10, ge=1, le=100)):
    try:
        return AnalyticsService.fetch_sellers(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sellers: {str(e)}")

@router.get("/delivery", response_model=List[DeliverySLAItem])
def get_delivery():
    try:
        return AnalyticsService.fetch_delivery_performance()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch delivery analytics: {str(e)}")

@router.get("/payments", response_model=List[PaymentItem])
def get_payments():
    try:
        return AnalyticsService.fetch_payments()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch payment analytics: {str(e)}")
