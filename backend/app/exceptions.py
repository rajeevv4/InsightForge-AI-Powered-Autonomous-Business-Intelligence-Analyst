"""
InsightForge — Core Custom Exceptions
"""

class DatabaseUnavailableError(Exception):
    """
    Raised when the PostgreSQL database connection fails and fixture fallback
    is disallowed (USE_FIXTURES != 1).
    """
    pass


class QueryTimeoutError(Exception):
    """
    Raised when a PostgreSQL query times out (e.g. statement_timeout)
    and fixture fallback is disallowed (USE_FIXTURES != 1).
    """
    pass

