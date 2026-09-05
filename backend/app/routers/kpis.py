from fastapi import APIRouter, HTTPException
from backend.app.schemas.kpis import KPISummaryResponse
from backend.app.services.analytics_service import AnalyticsService

router = APIRouter(tags=["KPIs"])

@router.get("/kpis", response_model=KPISummaryResponse)
def get_kpis():
    try:
        data = AnalyticsService.fetch_canonical_kpis()
        return KPISummaryResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch canonical KPIs: {str(e)}")
