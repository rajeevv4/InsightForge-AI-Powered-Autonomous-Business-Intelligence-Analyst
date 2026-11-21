import logging
from fastapi import APIRouter, HTTPException
from backend.app.schemas.kpis import KPISummaryResponse
from backend.app.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["KPIs"])

@router.get("/kpis", response_model=KPISummaryResponse)
def get_kpis():
    try:
        data = AnalyticsService.fetch_canonical_kpis()
        return KPISummaryResponse(**data)
    except Exception as e:
        logger.error(f"Failed to fetch canonical KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch executive KPIs. Please try again later.")
