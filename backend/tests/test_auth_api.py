"""Authentication API tests: registration, login, refresh rotation, revocation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models import RefreshToken, User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def _register(client: TestClient, email: str = "a@example.com", password: str = "Sunflower2026"):
    return client.post(
        REGISTER,
        json={"email": email, "password": password, "full_name": "Test Farmer"},
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_returns_token_pair_and_never_the_password(client: TestClient, session: Session):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert "password" not in str(body).lower()

    user = session.scalar(select(User).where(User.email == "a@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$2b$")  # bcrypt
    assert "Sunflower2026" not in user.password_hash


def test_register_normalises_email_to_lowercase(client: TestClient, session: Session):
    response = client.post(
        REGISTER,
        json={"email": "MiXeD@Example.COM", "password": "Sunflower2026", "full_name": "X"},
    )
    assert response.status_code == 201
    assert session.scalar(select(User).where(User.email == "mixed@example.com")) is not None


def test_register_rejects_duplicate_email(client: TestClient):
    assert _register(client).status_code == 201
    second = _register(client)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize(
    ("password", "reason"),
    [
        ("short1", "too short"),
        ("allletters", "no digits"),
        ("12345678", "no letters"),
        ("password1", "too common"),
    ],
)
def test_register_rejects_weak_passwords(client: TestClient, password: str, reason: str):
    response = client.post(
        REGISTER,
        json={"email": "weak@example.com", "password": password, "full_name": "Weak"},
    )
    assert response.status_code == 422, reason


def test_register_rejects_unknown_fields(client: TestClient):
    response = client.post(
        REGISTER,
        json={
            "email": "x@example.com",
            "password": "Sunflower2026",
            "full_name": "X",
            "is_admin": True,  # privilege escalation attempt
        },
    )
    assert response.status_code == 422


def test_register_validates_email_format(client: TestClient):
    response = client.post(
        REGISTER, json={"email": "not-an-email", "password": "Sunflower2026", "full_name": "X"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_succeeds_with_correct_credentials(client: TestClient):
    _register(client)
    response = client.post(LOGIN, json={"email": "a@example.com", "password": "Sunflower2026"})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_is_case_insensitive_on_email(client: TestClient):
    _register(client)
    response = client.post(LOGIN, json={"email": "A@EXAMPLE.COM", "password": "Sunflower2026"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "a@example.com", "password": "WrongPassword1"},
        {"email": "nobody@example.com", "password": "Sunflower2026"},
    ],
)
def test_login_failure_is_indistinguishable(client: TestClient, payload: dict):
    """Both cases must return the same message, or the API enumerates accounts."""
    _register(client)
    response = client.post(LOGIN, json=payload)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Email or password is incorrect."


# ---------------------------------------------------------------------------
# Protected routes
# ---------------------------------------------------------------------------
def test_me_requires_authentication(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_me_rejects_malformed_token(client: TestClient):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_me_accepts_valid_token(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "farmer@example.com"


def test_refresh_token_cannot_be_used_as_access_token(client: TestClient):
    tokens = _register(client).json()
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Refresh rotation
# ---------------------------------------------------------------------------
def test_refresh_rotates_the_token_and_old_one_stops_working(client: TestClient):
    tokens = _register(client).json()

    first = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    rotated = first.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # Replaying the original token must fail: it was revoked on use.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reused"

    second = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert second.status_code == 200


def test_refresh_rejects_unknown_token(client: TestClient):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40})
    assert response.status_code == 401


def test_refresh_rejects_expired_token(client: TestClient, session: Session):
    tokens = _register(client).json()
    record = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(tokens["refresh_token"]))
    )
    record.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.commit()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


def test_logout_revokes_the_refresh_token(client: TestClient):
    tokens = _register(client).json()
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_logout_all_invalidates_existing_access_tokens(client: TestClient, auth_headers: dict):
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200
    assert client.post("/api/v1/auth/logout-all", headers=auth_headers).status_code == 200

    # The same access token must now be rejected: token_version changed.
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_revoked"


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def test_update_profile_language_and_theme(client: TestClient, auth_headers: dict):
    response = client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"preferred_language": "ur", "theme": "dark"},
    )
    assert response.status_code == 200
    assert response.json()["preferred_language"] == "ur"
    assert response.json()["theme"] == "dark"


def test_update_profile_rejects_invalid_language(client: TestClient, auth_headers: dict):
    response = client.patch(
        "/api/v1/auth/me", headers=auth_headers, json={"preferred_language": "fr"}
    )
    assert response.status_code == 422


def test_change_password_requires_current_password(client: TestClient, auth_headers: dict):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={"current_password": "WrongPassword1", "new_password": "NewSunflower2026"},
    )
    assert response.status_code == 401


def test_change_password_works_and_invalidates_sessions(client: TestClient, auth_headers: dict):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={"current_password": "Sunflower2026", "new_password": "NewSunflower2026"},
    )
    assert response.status_code == 200

    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401
    login = client.post(
        LOGIN, json={"email": "farmer@example.com", "password": "NewSunflower2026"}
    )
    assert login.status_code == 200


def test_change_password_rejects_reusing_the_same_password(client: TestClient, auth_headers: dict):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={"current_password": "Sunflower2026", "new_password": "Sunflower2026"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def test_login_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    payload = {"email": "a@example.com", "password": "WrongPassword1"}
    statuses = [client.post(LOGIN, json=payload).status_code for _ in range(4)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429
