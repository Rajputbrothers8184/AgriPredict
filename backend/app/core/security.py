"""Password hashing and JWT creation/verification.

Design notes
------------
* bcrypt is used directly (not passlib) because bcrypt 4.x dropped the
  ``__about__`` attribute that passlib 1.7 expects, which produces a noisy but
  harmless warning on every hash. Calling bcrypt keeps the dependency surface and
  the logs clean.
* bcrypt truncates at 72 bytes; longer passwords are rejected explicitly rather
  than silently ignored.
* Refresh tokens are opaque random strings. Only their SHA-256 hash is stored,
  so a database leak does not hand out sessions.
* ``token_version`` on the user row is embedded in the access token and compared
  on every request, which makes "log out everywhere" and password changes
  effective immediately without a token blacklist.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import re

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import AuthError

BCRYPT_MAX_BYTES = 72
MIN_PASSWORD_LENGTH = 8

# Passwords that are seen in every credential-stuffing list. Matching is done on
# the value with any trailing digits stripped, so "password1" is caught too.
COMMON_PASSWORDS = {
    "password", "passw0rd", "12345678", "123456789", "qwerty123", "qwertyuiop",
    "iloveyou", "letmein", "welcome", "admin", "administrator", "agripredict",
    "farmer", "pakistan", "abc12345", "test1234", "changeme",
}
DIGITS_SUFFIX = re.compile(r"\d+$")

TokenType = Literal["access", "refresh", "report_download"]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def validate_password_strength(password: str) -> None:
    """Raise ``ValueError`` with a user-facing message if the password is weak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long (maximum 72 bytes).")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or DIGITS_SUFFIX.sub("", lowered) in COMMON_PASSWORDS:
        raise ValueError("Password is too common. Choose something less predictable.")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("Password must contain both letters and digits.")


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError("Password is too long (maximum 72 bytes).")
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish verification that never raises on malformed hashes."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _encode(subject: str, token_type: TokenType, expires_delta: timedelta, **claims: Any) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.app_name,
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, token_version: int, role: str = "farmer") -> str:
    return _encode(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        ver=token_version,
        role=role,
    )


def create_refresh_token(user_id: int, token_version: int) -> tuple[str, str, datetime]:
    """Return ``(plaintext_token, sha256_hash, expires_at)``.

    The plaintext is returned to the client exactly once and never stored.
    """
    plaintext = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return plaintext, hash_token(plaintext), expires_at


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT, raising ``AuthError`` on any problem."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired. Please sign in again.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Token is invalid.", code="invalid_token") from exc

    if payload.get("type") != expected_type:
        raise AuthError(
            f"Expected a {expected_type} token.", code="invalid_token_type"
        )
    return payload


def create_report_download_token(user_id: int, report_id: int, ttl_minutes: int) -> str:
    """Mint a short-lived, single-purpose token for one report download.

    Why this exists: the download endpoint is authenticated with a bearer
    header, but the mobile app hands the URL to the system browser/download
    manager, which cannot send custom headers. Embedding the file URL in a
    signed query parameter lets the browser fetch it without ever exposing the
    long-lived access token.

    The token is deliberately narrow: it names one report, expires on its own,
    and is rejected by every other endpoint because ``decode_token`` checks the
    ``type`` claim against the expected value.
    """
    return _encode(
        str(user_id),
        "report_download",
        timedelta(minutes=ttl_minutes),
        report=int(report_id),
    )


def decode_report_download_token(token: str) -> dict[str, Any]:
    """Validate a report-download token and return its claims."""
    return decode_token(token, expected_type="report_download")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
