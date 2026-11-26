import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.config import settings
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError
from backend.app.limiter import limiter
from backend.app.routers import health, kpis, analytics, data_quality, ai, anomalies, voice, datasets
from backend.app.routers import forecast, report, briefing

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="REST API layer connecting PostgreSQL e-commerce data and analytics engine to InsightForge clients.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Register slowapi rate limiter state and exception handler
app.state.limiter = limiter


def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """slowapi's default 429 body plus a `detail` key (the shape the frontend reads for every error)."""
    response = _rate_limit_exceeded_handler(request, exc)
    body = {"error": f"Rate limit exceeded: {exc.detail}",
            "detail": f"Too many requests (limit: {exc.detail}). Please wait a moment and try again."}
    out = JSONResponse(body, status_code=429)
    for k, v in response.headers.items():
        if k.lower().startswith("x-ratelimit") or k.lower() == "retry-after":
            out.headers[k] = v
    return out


app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Register QueryTimeoutError exception handler (504 Gateway Timeout)
@app.exception_handler(QueryTimeoutError)
async def query_timeout_handler(request: Request, exc: QueryTimeoutError):
    logger.error(f"Query timed out on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=504,
        content={"detail": "Query timed out, please retry"}
    )

# Register DatabaseUnavailableError exception handler (503 Service Unavailable)
@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_handler(request: Request, exc: DatabaseUnavailableError):
    logger.error(f"Database unavailable on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable"}
    )

# Configure Development CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handler (Hides database credentials & sensitive stack traces)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )

# Include Router Modules under /api prefix
app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(kpis.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(data_quality.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)
app.include_router(anomalies.router, prefix=settings.API_PREFIX)
app.include_router(voice.router, prefix=settings.API_PREFIX)
app.include_router(datasets.router, prefix=settings.API_PREFIX)
app.include_router(forecast.router, prefix=settings.API_PREFIX)
app.include_router(report.router, prefix=settings.API_PREFIX)
app.include_router(briefing.router, prefix=settings.API_PREFIX)

@app.on_event("startup")
def _warm_data_quality_cache():
    """Pre-compute the (slow on remote DBs) data-quality audit so the first page load is instant."""
    import threading
    from backend.app.fixture_guard import is_fixture_mode_allowed
    from backend.app.services.data_quality_service import DataQualityService

    if is_fixture_mode_allowed():
        return

    def _run():
        try:
            DataQualityService.fetch_audit_summary()
            logger.info("Data-quality audit cache warmed.")
        except Exception as e:  # DB down at boot: requests will retry and surface 503s normally
            logger.warning(f"Data-quality cache warm-up skipped: {e}")

    threading.Thread(target=_run, name="dq-cache-warmup", daemon=True).start()


@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/api/health"
    }
