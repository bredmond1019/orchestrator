"""API key authentication dependency for the FastAPI application.

All protected routes depend on ``require_api_key``; unauthenticated routes
(``GET /health``, ``GET /workflows*``) do not include this dependency so
they remain publicly accessible.

The expected key is read from the ``ORCHESTRATION_API_KEY`` environment
variable at request time.  If the variable is unset the service returns
503 (fail-closed, not 401) so an operator misconfiguration is
distinguishable from a bad key.  Key comparison uses
``hmac.compare_digest`` to avoid timing-based side-channel attacks.
"""

import hmac
import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str | None = Header(None)) -> None:
    """FastAPI dependency that enforces ``X-API-Key`` authentication.

    The header is declared optional at the FastAPI level so that a missing
    header returns ``401`` rather than FastAPI's default ``422 Unprocessable
    Entity``.  The ``None`` check below produces the correct ``401``.

    Args:
        x_api_key: Value of the ``X-API-Key`` request header, or ``None``
            if the header is absent.

    Raises:
        HTTPException 503: ``ORCHESTRATION_API_KEY`` env var is unset
            (operator misconfiguration — fail-closed).
        HTTPException 401: Header is missing or does not match the
            configured key.
    """
    expected = os.environ.get("ORCHESTRATION_API_KEY")
    if expected is None:
        raise HTTPException(
            status_code=503,
            detail="Service not configured: ORCHESTRATION_API_KEY is unset.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )
