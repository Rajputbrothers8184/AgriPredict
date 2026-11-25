"""Shared FastAPI dependencies: authentication and rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError, RateLimitError
from app.core.security import decode_token
from app.database import get_db
from app.models import User

# auto_error=False so a missing header produces our consistent error envelope
# rather than FastAPI's default shape.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
) -> User:
    """Resolve the bearer token to an active user, rejecting stale token versions."""
    if credentials is None or not credentials.credentials:
        raise AuthError("Authentication credentials were not provided.")
    if credentials.scheme.lower() != "bearer":
        raise AuthError(
            "Unsupported authentication scheme.", code="unsupported_auth_scheme"
        )

    payload = decode_token(credentials.credentials, expected_type="access")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("Token subject is invalid.", code="invalid_token") from exc

    user = session.get(User, user_id)
    if user is None:
        raise AuthError("Account no longer exists.", code="account_missing")
    if not user.is_active:
        raise AuthError("This account has been deactivated.", code="account_inactive")
    if payload.get("ver") != user.token_version:
        raise AuthError(
            "Session has been invalidated. Please sign in again.", code="token_revoked"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# In-memory rate limiting
# ---------------------------------------------------------------------------
# Deliberately simple: a fixed window per client key held in process memory.
# It protects a single-process deployment against credential-stuffing, which is
# the realistic threat for this project. It is NOT shared across workers, so a
# multi-worker deployment should move this to Redis — recorded as a limitation.
_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, *, scope: str, limit: int | None = None, window: int = 60) -> None:
    """Raise ``RateLimitError`` when a client exceeds ``limit`` calls per window."""
    max_calls = limit or settings.auth_rate_limit_per_minute
    client = request.client.host if request.client else "unknown"
    key = f"{scope}:{client}"
    now = time.monotonic()
    bucket = _buckets[key]

    while bucket and now - bucket[0] > window:
        bucket.popleft()

    if len(bucket) >= max_calls:
        retry_after = int(window - (now - bucket[0])) + 1
        raise RateLimitError(
            f"Too many requests. Try again in {retry_after} seconds.",
            details={"retry_after_seconds": retry_after},
        )
    bucket.append(now)


def auth_rate_limiter(request: Request) -> None:
    """Dependency for the login/register endpoints."""
    rate_limit(request, scope="auth")


def reset_rate_limits() -> None:
    """Test helper: clear all buckets."""
    _buckets.clear()
