from urllib.parse import quote_plus
from sqlalchemy import create_engine, text, event
from backend.app.config import settings


def get_db_url() -> str:
    user = quote_plus(settings.DB_USER) if settings.DB_USER else ""
    if settings.DB_PASSWORD:
        password = quote_plus(settings.DB_PASSWORD)
        return f"postgresql://{user}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return f"postgresql://{user}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


def get_readonly_db_url() -> str:
    if not settings.DB_RO_USER or not settings.DB_RO_PASSWORD:
        raise RuntimeError(
            "Read-only database engine configuration missing: DB_RO_USER and DB_RO_PASSWORD must both be explicitly set. "
            "Silent fallback to read-write credentials is strictly forbidden."
        )
    user = quote_plus(settings.DB_RO_USER)
    password = quote_plus(settings.DB_RO_PASSWORD)
    return f"postgresql://{user}:{password}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


# Primary write/admin engine
engine = create_engine(get_db_url(), echo=False, pool_pre_ping=True)


@event.listens_for(engine, "connect")
def _set_rw_session(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SET search_path TO {settings.DB_SCHEMA}, public;")
    finally:
        cursor.close()


def _create_readonly_engine():
    ro_url = get_readonly_db_url()
    eng = create_engine(ro_url, echo=False, pool_pre_ping=True)

    @event.listens_for(eng, "connect")
    def _set_ro_session(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET search_path TO {settings.DB_SCHEMA}, public;")
            cursor.execute("SET statement_timeout = 5000;")
        finally:
            cursor.close()

    return eng


class _LazyEngineProxy:
    """Lazy engine proxy so imports and test setups without RO credentials do not fail immediately."""
    def __init__(self, factory):
        self._factory = factory
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = self._factory()
        return self._engine

    def connect(self, *args, **kwargs):
        return self._get_engine().connect(*args, **kwargs)

    def begin(self, *args, **kwargs):
        return self._get_engine().begin(*args, **kwargs)

    def execute(self, *args, **kwargs):
        return self._get_engine().execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._get_engine(), name)


# Read-only engine proxy (lazily instantiated on first use)
readonly_engine = _LazyEngineProxy(_create_readonly_engine)


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1")).scalar()
            return res == 1
    except Exception:
        return False
