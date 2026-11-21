import logging
from fastapi import APIRouter, HTTPException
from backend.app.schemas.data_quality import DataQualityResponse
from backend.app.services.data_quality_service import DataQualityService
from backend.app.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Data Quality"])

@router.get("/data-quality", response_model=DataQualityResponse)
def get_data_quality():
    try:
        data = DataQualityService.fetch_audit_summary()
        return DataQualityResponse(**data)
    except DatabaseUnavailableError as e:
        logger.error(f"Database unavailable in /data-quality: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch data quality report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch data quality report. Please try again later.")
