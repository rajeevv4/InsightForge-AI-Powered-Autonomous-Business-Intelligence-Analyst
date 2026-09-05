from sqlalchemy import create_engine, text
from backend.app.config import settings

def get_db_url() -> str:
    if settings.DB_PASSWORD:
        return f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return f"postgresql://{settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

engine = create_engine(get_db_url(), echo=False, pool_pre_ping=True)

def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {settings.DB_SCHEMA}, public;"))
            res = conn.execute(text("SELECT 1")).scalar()
            return res == 1
    except Exception:
        return False
