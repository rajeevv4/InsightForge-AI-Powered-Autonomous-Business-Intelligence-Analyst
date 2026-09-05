from fastapi import APIRouter, HTTPException
from backend.app.schemas.data_quality import DataQualityResponse
from backend.app.services.data_quality_service import DataQualityService

router = APIRouter(tags=["Data Quality"])

@router.get("/data-quality", response_model=DataQualityResponse)
def get_data_quality():
    try:
        data = DataQualityService.fetch_audit_summary()
        return DataQualityResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch data quality report: {str(e)}")
