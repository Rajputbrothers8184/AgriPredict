"""Authentication: registration, login, refresh rotation and password change."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AuthError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas import TokenPair, UserCreate

logger = logging.getLogger(__name__)


def _issue_tokens(session: Session, user: User) -> TokenPair:
    access = create_access_token(user.id, user.token_version, user.role)
    plaintext, token_hash, expires_at = create_refresh_token(user.id, user.token_version)
    session.add(
        RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    )
    return TokenPair(
        access_token=access,
        refresh_token=plaintext,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def register_user(session: Session, payload: UserCreate) -> tuple[User, TokenPair]:
    """Create an account and sign the user in immediately."""
    try:
        validate_password_strength(payload.password)
    except ValueError as exc:
        raise ValidationError(str(exc), details={"field": "password"}) from exc

    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        # Deliberately explicit: this endpoint is the registration form, where
        # "email already registered" is the expected, helpful message. The login
        # endpoint stays generic to avoid account enumeration.
        raise ConflictError(
            "An account with this email already exists.", code="email_taken"
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        preferred_language=payload.preferred_language,
    )
    session.add(user)
    session.flush()  # assign user.id before creating tokens
    tokens = _issue_tokens(session, user)
    session.commit()
    session.refresh(user)
    logger.info("registered user id=%s", user.id)
    return user, tokens


def authenticate(session: Session, email: str, password: str) -> tuple[User, TokenPair]:
    """Verify credentials and issue a token pair.

    The same error is returned for "unknown email" and "wrong password" so the
    endpoint cannot be used to enumerate accounts.
    """
    user = session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise AuthError("This account has been deactivated.", code="account_inactive")
    tokens = _issue_tokens(session, user)
    session.commit()
    return user, tokens


def refresh_session(session: Session, refresh_token: str) -> TokenPair:
    """Exchange a refresh token for a new pair, rotating the old one.

    Rotation makes a stolen token single-use: the legitimate client's next refresh
    fails after the thief has used it, which surfaces the compromise.
    """
    token_hash = hash_token(refresh_token)
    record = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if record is None:
        raise AuthError("Refresh token is not recognised.", code="invalid_refresh_token")

    now = datetime.now(timezone.utc)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:  # SQLite round-trip loses tzinfo
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if record.revoked_at is not None:
        raise AuthError("Refresh token has already been used.", code="refresh_token_reused")
    if expires_at < now:
        raise AuthError("Refresh token has expired. Please sign in again.", code="token_expired")

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("Account is not available.", code="account_inactive")

    record.revoked_at = now
    tokens = _issue_tokens(session, user)
    session.commit()
    return tokens


def revoke_refresh_token(session: Session, refresh_token: str) -> None:
    token_hash = hash_token(refresh_token)
    record = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        session.commit()


def revoke_all_user_tokens(session: Session, user: User) -> None:
    """Invalidate every session: bump the token version and revoke refresh rows."""
    user.token_version += 1
    now = datetime.now(timezone.utc)
    for record in session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ):
        record.revoked_at = now
    session.commit()


def change_password(session: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise InvalidCredentialsError("Current password is incorrect.")
    try:
        validate_password_strength(new)
    except ValueError as exc:
        raise ValidationError(str(exc), details={"field": "new_password"}) from exc
    if verify_password(new, user.password_hash):
        raise ValidationError(
            "New password must be different from the current password.",
            details={"field": "new_password"},
        )
    user.password_hash = hash_password(new)
    # Password change must end existing sessions.
    revoke_all_user_tokens(session, user)


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def validate_access_payload(payload: dict) -> User:
    """Placeholder kept for symmetry with decode_token; see ``app.api.deps``."""
    raise NotImplementedError("Access validation lives in app.api.deps")
