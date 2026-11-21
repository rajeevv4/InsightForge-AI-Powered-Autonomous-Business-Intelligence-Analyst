from fastapi import APIRouter
from backend.app.schemas.health import HealthResponse
from backend.app.database import check_db_connection
from backend.app.config import settings
from backend.app.fixture_guard import is_fixture_mode_allowed

router = APIRouter(tags=["Health"])

@router.get("/health", response_model=HealthResponse)
def get_health():
    db_ok = check_db_connection()
    use_fixtures = is_fixture_mode_allowed()

    # Truthfully report database status
    database_status = "connected" if db_ok else "disconnected"

    # Truthfully report active data source
    data_source = "postgres" if db_ok else ("fixture" if use_fixtures else "postgres")

    if db_ok:
        status = "healthy"
    elif use_fixtures:
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        database=database_status,
        data_source=data_source,
        service="InsightForge",
        version=settings.VERSION
    )
