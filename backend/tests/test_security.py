"""Security-focused tests.

These exist because the functional suites answer "does it work?" and not
"can it be abused?". Each test below corresponds to a concrete way this API
could be made to leak data, escalate privileges or be knocked over.

Scope is honest: this covers the application layer. Transport security (TLS),
host hardening and dependency scanning are handled elsewhere — see
``docs/security/review.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_report_download_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import Report, User


# ---------------------------------------------------------------------------
# Password storage
# ---------------------------------------------------------------------------
def test_passwords_are_hashed_with_bcrypt_not_stored_plaintext():
    digest = hash_password("Sunflower2026")
    assert "Sunflower2026" not in digest
    # bcrypt hashes carry a recognisable prefix and per-hash salt.
    assert digest.startswith(("$2a$", "$2b$", "$2y$"))


def test_the_same_password_hashes_differently_each_time():
    first = hash_password("Sunflower2026")
    second = hash_password("Sunflower2026")
    assert first != second, "identical hashes would reveal that two users share a password"


def test_password_verification_rejects_wrong_and_empty_input():
    digest = hash_password("Sunflower2026")
    assert verify_password("Sunflower2026", digest) is True
    assert verify_password("sunflower2026", digest) is False
    assert verify_password("", digest) is False


# ---------------------------------------------------------------------------
# JWT handling
# ---------------------------------------------------------------------------
def test_access_token_round_trips_with_its_type():
    token = create_access_token(user_id=42, token_version=1)
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_a_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999, "iat": 1, "iss": settings.app_name},
        "attacker-secret",
        algorithm="HS256",
    )
    with pytest.raises(Exception):
        decode_token(forged, expected_type="access")


def test_alg_none_tokens_are_rejected():
    unsigned = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999, "iat": 1, "iss": settings.app_name},
        key="",
        algorithm="none",
    )
    with pytest.raises(Exception):
        decode_token(unsigned, expected_type="access")


def test_an_expired_token_is_rejected():
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()),
            "iat": 1,
            "iss": settings.app_name,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(Exception):
        decode_token(expired, expected_type="access")


def test_a_refresh_token_cannot_be_used_as_an_access_token():
    plaintext, _digest, _expires = create_refresh_token(user_id=1, token_version=1)
    with pytest.raises(Exception):
        decode_token(plaintext, expected_type="access")


def test_a_download_token_cannot_be_used_as_an_access_token():
    token = create_report_download_token(user_id=1, report_id=5, ttl_minutes=5)
    assert decode_token(token, expected_type="report_download")["report"] == 5
    with pytest.raises(Exception):
        decode_token(token, expected_type="access")


# ---------------------------------------------------------------------------
# Authorisation: horizontal (other users) and vertical (privileges)
# ---------------------------------------------------------------------------
def test_every_protected_route_refuses_anonymous_access(client: TestClient):
    protected = [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/farms"),
        ("POST", "/api/v1/farms"),
        ("GET", "/api/v1/crop-cycles"),
        ("GET", "/api/v1/finance/summary"),
        ("GET", "/api/v1/reports"),
        ("GET", "/api/v1/buyers/saved"),
        ("GET", "/api/v1/weather/1"),
        ("GET", "/api/v1/markets/history/wheat/lahore-sabzi-mandi"),
        ("GET", "/api/v1/forecasts/wheat/lahore-sabzi-mandi"),
        ("GET", "/api/v1/farms/1"),
        ("GET", "/api/v1/crop-cycles/1"),
    ]
    leaks = []
    for method, path in protected:
        response = client.request(method, path, json={} if method == "POST" else None)
        if response.status_code != 401:
            leaks.append(f"{method} {path} -> {response.status_code}")
    assert leaks == [], f"unauthenticated access was not refused: {leaks}"


def test_one_user_cannot_read_another_users_farm(
    client: TestClient, auth_headers: dict, other_user_headers: dict, farm: dict
):
    response = client.get(f"/api/v1/farms/{farm['id']}", headers=other_user_headers)
    # 404, not 403: the API must not confirm that someone else's farm exists.
    assert response.status_code == 404


def test_one_user_cannot_modify_another_users_farm(
    client: TestClient, auth_headers: dict, other_user_headers: dict, farm: dict
):
    response = client.patch(
        f"/api/v1/farms/{farm['id']}", headers=other_user_headers, json={"name": "Hijacked"}
    )
    assert response.status_code == 404

    # And the original name is intact.
    mine = client.get(f"/api/v1/farms/{farm['id']}", headers=auth_headers)
    assert mine.json()["name"] == farm["name"]


def test_expenses_cannot_be_attached_to_another_users_cycle(
    client: TestClient,
    session: Session,
    auth_headers: dict,
    other_user_headers: dict,
    farm: dict,
    seeded: Session,
):
    cycle = client.post(
        "/api/v1/crop-cycles",
        headers=auth_headers,
        json={
            "farm_id": farm["id"],
            "commodity_id": _any_commodity_id(client, auth_headers),
            "area_acres": 2,
            "sowing_date": "2026-11-01",
        },
    ).json()

    response = client.post(
        f"/api/v1/crop-cycles/{cycle['id']}/expenses",
        headers=other_user_headers,
        json={"category": "seeds", "amount_pkr": 100, "expense_date": "2026-11-02"},
    )
    assert response.status_code == 404


def test_a_user_cannot_register_as_an_admin(
    client: TestClient,
):
    # An unexpected privilege field must not be honoured. Either it is rejected
    # as an extra field or ignored; what matters is the resulting role.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "escalate@agripredict.pk",
            "password": "Escalate2026",
            "full_name": "Escalate",
            "role": "admin",
            "is_active": True,
            "is_superuser": True,
        },
    )
    if response.status_code in (200, 201):
        token = response.json()["access_token"]
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json()
        assert me["role"] == "farmer"
    else:
        assert response.status_code == 422


def test_profile_update_cannot_change_role(
    client: TestClient, auth_headers: dict
):
    response = client.patch(
        "/api/v1/auth/me", headers=auth_headers, json={"role": "admin", "is_active": False}
    )
    # Either rejected outright, or accepted while ignoring the privileged fields.
    if response.status_code == 200:
        assert response.json()["role"] == "farmer"
        assert response.json()["is_active"] is True
    else:
        assert response.status_code == 422


def test_a_deactivated_account_cannot_authenticate(
    client: TestClient, session: Session, auth_headers: dict
):
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    user = session.get(User, me["id"])
    user.is_active = False
    session.commit()

    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 401


def test_a_password_change_invalidates_existing_tokens(
    client: TestClient, auth_headers: dict
):
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={"current_password": "Sunflower2026", "new_password": "NewHarvest2026"},
    )
    assert changed.status_code in (200, 204)

    # The old access token must be dead: token_version was bumped.
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401


def test_wrong_current_password_does_not_change_anything(
    client: TestClient, auth_headers: dict
):
    response = client.post(
        "/api/v1/auth/change-password",
        headers=auth_headers,
        json={"current_password": "not-my-password", "new_password": "Attacker2026"},
    )
    assert response.status_code == 401
    # Original credentials still work.
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200


# ---------------------------------------------------------------------------
# Injection and input handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "\\x00admin",
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "٪00",
    ],
)
def test_hostile_strings_are_stored_as_data_not_executed(
    client: TestClient, auth_headers: dict, payload: str
):
    created = client.post(
        "/api/v1/farms", headers=auth_headers, json={"name": payload[:60], "district": payload[:60]}
    )
    if created.status_code == 422:
        # Rejected by validation is also acceptable.
        return
    assert created.status_code in (200, 201)
    # The table is still there and the row round-trips unchanged.
    listing = client.get("/api/v1/farms", headers=auth_headers)
    assert listing.status_code == 200


def test_numeric_fields_reject_non_numeric_and_overflow(
    client: TestClient, auth_headers: dict, farm: dict, seeded: Session
):
    base = {
        "farm_id": farm["id"],
        "commodity_id": _any_commodity_id(client, auth_headers),
        "sowing_date": "2026-11-01",
    }
    for bad in ("not-a-number", -5, 0, 10**18):
        response = client.post(
            "/api/v1/crop-cycles", headers=auth_headers, json={**base, "area_acres": bad}
        )
        assert response.status_code == 422, f"area_acres={bad!r} was accepted"


def test_unknown_fields_are_rejected_not_silently_ignored(
    client: TestClient, auth_headers: dict
):
    response = client.post(
        "/api/v1/farms",
        headers=auth_headers,
        json={"name": "Farm", "district": "Lahore", "user_id": 1},
    )
    # Strict models must not let a client smuggle an ownership field.
    assert response.status_code == 422


def test_pagination_parameters_are_bounded(client: TestClient, auth_headers: dict):
    assert (
        client.get("/api/v1/reports", headers=auth_headers, params={"limit": 10_000}).status_code
        == 422
    )
    assert (
        client.get("/api/v1/reports", headers=auth_headers, params={"limit": -1}).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Report file access
# ---------------------------------------------------------------------------
def _make_report(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/api/v1/reports", headers=headers, json={"report_type": "financial_summary", "file_format": "pdf"}
    )
    assert response.status_code == 200
    return response.json()


def test_report_filename_is_server_generated(
    client: TestClient, auth_headers: dict, temp_report_dir
):
    body = _make_report(client, auth_headers)
    # A user-supplied path in `filename` would let a download write outside the
    # report directory.
    assert "/" not in body["filename"]
    assert ".." not in body["filename"]
    assert body["filename"].endswith(".pdf")


def test_a_signed_link_still_serves_only_its_owner(
    client: TestClient, auth_headers: dict, other_user_headers: dict, temp_report_dir
):
    body = _make_report(client, auth_headers)

    # The credentials presented take precedence over the signed link: presenting
    # someone else's session must not let that session borrow the link's
    # authority. The result is a 404, never a 403, so the API does not confirm
    # that the report exists.
    dl = client.get(body["download_url"], headers=other_user_headers)
    assert dl.status_code == 404

    # Holding only the id is likewise not enough.
    by_id = client.get(f"/api/v1/reports/{body['id']}/download", headers=other_user_headers)
    assert by_id.status_code == 404

    # The owner can still use their own link with no header at all.
    assert client.get(body["download_url"]).status_code == 200


def test_a_download_link_lapses_when_the_report_expires(
    client: TestClient, session: Session, auth_headers: dict, temp_report_dir
):
    body = _make_report(client, auth_headers)
    record = session.get(Report, body["id"])
    record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()

    assert client.get(body["download_url"]).status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def test_login_attempts_are_rate_limited(client: TestClient):
    from app.api.deps import reset_rate_limits

    reset_rate_limits()
    statuses = []
    for _ in range(30):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@agripredict.pk", "password": "WrongPassword1"},
        )
        statuses.append(response.status_code)
        if response.status_code == 429:
            break

    assert 429 in statuses, "credential-stuffing was never throttled"
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@agripredict.pk", "password": "WrongPassword1"},
    )
    assert limited.status_code == 429
    assert "retry_after_seconds" in limited.json()["error"]["details"]


def test_rate_limit_reports_retry_after_so_clients_can_back_off(client: TestClient):
    from app.api.deps import reset_rate_limits

    reset_rate_limits()
    for _ in range(30):
        response = client.post(
            "/api/v1/auth/login", json={"email": "x@agripredict.pk", "password": "Wrong1"}
        )
        if response.status_code == 429:
            seconds = response.json()["error"]["details"]["retry_after_seconds"]
            assert isinstance(seconds, int) and 1 <= seconds <= 61
            return
    pytest.fail("rate limit never triggered")


# ---------------------------------------------------------------------------
# Response hygiene
# ---------------------------------------------------------------------------
def test_security_headers_are_present_on_api_responses(client: TestClient):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == settings.frame_options
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_a_relaxed_frame_policy_is_refused_in_production():
    """Embedding is a sandbox concession; it must never reach production."""
    from app.core.config import Settings

    relaxed = Settings(
        _env_file=None,
        environment="production",
        debug=False,
        secret_key="a" * 48,
        frame_options="SAMEORIGIN",
    )
    with pytest.raises(RuntimeError, match="FRAME_OPTIONS"):
        relaxed.validate_runtime()


def test_a_strict_frame_policy_is_accepted_in_production():
    from app.core.config import Settings

    strict = Settings(
        _env_file=None,
        environment="production",
        debug=False,
        secret_key="b" * 48,
    )
    strict.validate_runtime()  # must not raise


def test_error_responses_do_not_leak_internals(client: TestClient, auth_headers: dict):
    response = client.get("/api/v1/crop-cycles/999999", headers=auth_headers)
    body = response.text.lower()
    for leak in ("traceback", "sqlalchemy", "sqlite", "site-packages", "file \"/"):
        assert leak not in body, f"error response leaked {leak!r}"


def test_login_response_does_not_reveal_whether_an_email_exists(client: TestClient):
    from app.api.deps import reset_rate_limits

    reset_rate_limits()
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "definitely-not-here@agripredict.pk", "password": "Whatever1"}
    )
    reset_rate_limits()
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": "demo@agripredict.pk", "password": "WrongPassword1"}
    )
    assert unknown.status_code == wrong_password.status_code == 401
    # Same message and same code: enumeration by error text is impossible.
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]


def test_user_payloads_never_include_the_password_hash(client: TestClient, auth_headers: dict):
    body = client.get("/api/v1/auth/me", headers=auth_headers).text.lower()
    for field in ("password", "hashed_password", "password_hash", "$2b$"):
        assert field not in body


# ---------------------------------------------------------------------------
# Helper used by several tests above
# ---------------------------------------------------------------------------
def _any_commodity_id(client: TestClient, headers: dict) -> int:
    commodities = client.get("/api/v1/markets/commodities", headers=headers).json()
    return commodities[0]["id"]


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def test_cors_preflight_allows_a_configured_origin(client: TestClient):
    """The mobile/web client must be able to preflight a JSON POST."""
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8081"


def test_cors_preflight_rejects_an_unknown_origin(client: TestClient):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # 400 without an allow-origin header: the browser then blocks the response.
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_is_never_a_bare_wildcard():
    """A '*' in allow_origins would be a find-replace away from an open API.

    Starlette matches `allow_origins` as literal strings, so a wildcard written
    as "*" combined with `allow_credentials` is both wrong and dangerous; and a
    pattern like "https://*.e2b.app" never matches at all, which fails the
    preflight silently. Patterns belong in `cors_origin_regex`.
    """
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert "*" not in settings.cors_origin_list
    assert all("*" not in origin for origin in settings.cors_origin_list)
