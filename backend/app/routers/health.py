from fastapi import APIRouter
from backend.app.schemas.health import HealthResponse
from backend.app.database import check_db_connection
from backend.app.config import settings

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
def get_health():
    db_ok = check_db_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        database="connected" if db_ok else "disconnected",
        service="InsightForge",
        version=settings.VERSION
    )
