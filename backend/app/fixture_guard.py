import os
from backend.app.exceptions import DatabaseUnavailableError, QueryTimeoutError


def is_fixture_mode_allowed() -> bool:
    """
    Checks if canonical fixture fallbacks are permitted.
    Per LEVEL 1.5 requirement:
    Fixtures are active ONLY when environment variable USE_FIXTURES=1.
    Otherwise, raise a clear DatabaseUnavailableError or QueryTimeoutError.
    """
    env_val = os.getenv("USE_FIXTURES", "").strip().lower()
    return env_val in ("1", "true", "yes")


def is_fixture_mode() -> bool:
    """Alias for is_fixture_mode_allowed()."""
    return is_fixture_mode_allowed()


def is_timeout_error(error: Exception) -> bool:
    """
    Returns True if the exception represents a query cancellation due to statement timeout.
    """
    if isinstance(error, QueryTimeoutError):
        return True

    orig = getattr(error, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(error, "pgcode", None)
    if pgcode == "57014":
        return True

    err_str = str(error).lower()
    if (
        "statement timeout" in err_str
        or "canceling statement due to statement timeout" in err_str
        or "query_canceled" in err_str
        or "query timed out" in err_str
        or "statement_timeout" in err_str
    ):
        return True
    return False


def assert_database_available(error: Exception, operation: str) -> None:
    """
    Raises QueryTimeoutError or DatabaseUnavailableError when PostgreSQL fails and USE_FIXTURES != 1.
    """
    if not is_fixture_mode_allowed():
        if is_timeout_error(error):
            raise QueryTimeoutError(
                f"Query timed out during '{operation}': {error}. "
                f"Statement timeout exceeded. Please retry."
            ) from error
        raise DatabaseUnavailableError(
            f"Database unavailable during '{operation}': {error}. "
            f"NO silent fake data is allowed. Live database connection is required. "
            f"To enable mock fixtures for offline testing or demo, set USE_FIXTURES=1 in your environment or .env."
        ) from error

