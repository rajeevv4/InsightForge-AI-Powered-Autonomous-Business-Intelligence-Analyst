from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from backend.app.config import settings


def get_db_url() -> str:
    user = quote_plus(settings.DB_USER) if settings.DB_USER else ""
    if settings.DB_PASSWORD:
        password = quote_plus(settings.DB_PASSWORD)
        return f"postgresql://{user}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return f"postgresql://{user}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


def get_readonly_db_url() -> str:
    raw_user = settings.DB_RO_USER or settings.DB_USER
    raw_password = settings.DB_RO_PASSWORD if settings.DB_RO_PASSWORD is not None else settings.DB_PASSWORD
    user = quote_plus(raw_user) if raw_user else ""
    if raw_password:
        password = quote_plus(raw_password)
        return f"postgresql://{user}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return f"postgresql://{user}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


# Primary write/admin engine
engine = create_engine(get_db_url(), echo=False, pool_pre_ping=True)

# Read-only engine for analytical queries with a strict 5-second statement timeout
readonly_engine = create_engine(
    get_readonly_db_url(),
    echo=False,
    pool_pre_ping=True,
    connect_args={"options": "-c statement_timeout=5000"}
)


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {settings.DB_SCHEMA}, public;"))
            res = conn.execute(text("SELECT 1")).scalar()
            return res == 1
    except Exception:
        return False
