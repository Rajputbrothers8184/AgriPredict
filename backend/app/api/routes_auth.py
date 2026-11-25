"""Authentication and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, auth_rate_limiter
from app.models import User
from app.schemas import (
    Message,
    PasswordChange,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserRead,
    UserUpdate,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    dependencies=[Depends(auth_rate_limiter)],
)
def register(payload: UserCreate, session: DbSession) -> TokenPair:
    _user, tokens = auth_service.register_user(session, payload)
    return tokens


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Sign in with email and password",
    dependencies=[Depends(auth_rate_limiter)],
)
def login(payload: UserLogin, session: DbSession) -> TokenPair:
    _user, tokens = auth_service.authenticate(session, payload.email, payload.password)
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    return auth_service.refresh_session(session, payload.refresh_token)


@router.post("/logout", response_model=Message, summary="Revoke a refresh token")
def logout(payload: RefreshRequest, session: DbSession) -> Message:
    auth_service.revoke_refresh_token(session, payload.refresh_token)
    return Message(message="Signed out.")


@router.post(
    "/logout-all", response_model=Message, summary="Revoke every session for this account"
)
def logout_all(session: DbSession, user: CurrentUser) -> Message:
    auth_service.revoke_all_user_tokens(session, user)
    return Message(message="Signed out on all devices.")


@router.get("/me", response_model=UserRead, summary="Current user profile")
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead, summary="Update profile, language or theme")
def update_me(payload: UserUpdate, session: DbSession, user: CurrentUser) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    session.commit()
    session.refresh(user)
    return user


@router.post("/change-password", response_model=Message, summary="Change password")
def change_password(
    payload: PasswordChange, session: DbSession, user: CurrentUser
) -> Message:
    auth_service.change_password(session, user, payload.current_password, payload.new_password)
    return Message(message="Password changed. Please sign in again on all devices.")
