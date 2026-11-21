from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from backend.app.config import settings


def get_client_ip(request: Request) -> str:
    """
    Extracts the client IP address.
    If TRUSTED_PROXIES_ENABLED is True, extracts the left-most client IP from the
    X-Forwarded-For header; otherwise, falls back to the direct TCP socket remote address.
    """
    if getattr(settings, "TRUSTED_PROXIES_ENABLED", False):
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            client_ip = x_forwarded.split(",")[0].strip()
            if client_ip:
                return client_ip
    return get_remote_address(request)


# Shared application rate limiter using proxy-aware client IP
limiter = Limiter(key_func=get_client_ip)
