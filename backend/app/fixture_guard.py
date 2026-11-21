import os
from backend.app.exceptions import DatabaseUnavailableError


def is_fixture_mode_allowed() -> bool:
    """
    Checks if canonical fixture fallbacks are permitted.
    Per LEVEL 1.5 requirement:
    Fixtures are active ONLY when environment variable USE_FIXTURES=1.
    Otherwise, raise a clear DatabaseUnavailableError.
    """
    env_val = os.getenv("USE_FIXTURES", "").strip().lower()
    return env_val in ("1", "true", "yes")


def is_fixture_mode() -> bool:
    """Alias for is_fixture_mode_allowed()."""
    return is_fixture_mode_allowed()


def assert_database_available(error: Exception, operation: str) -> None:
    """
    Raises a DatabaseUnavailableError when PostgreSQL is unreachable and USE_FIXTURES != 1.
    """
    if not is_fixture_mode_allowed():
        raise DatabaseUnavailableError(
            f"Database unavailable during '{operation}': {error}. "
            f"NO silent fake data is allowed. Live database connection is required. "
            f"To enable mock fixtures for offline testing or demo, set USE_FIXTURES=1 in your environment or .env."
        ) from error
