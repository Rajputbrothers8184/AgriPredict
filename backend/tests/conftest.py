"""Shared pytest fixtures.

Each test gets its own in-memory SQLite database, so tests are isolated and can
run in any order. ``StaticPool`` keeps the single connection alive so the schema
created by ``create_all`` is visible to the app's sessions.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

# Environment must be configured before the app package is imported, because
# ``app.core.config`` builds its settings singleton at import time.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-1234567890")
os.environ.setdefault("WEATHER_PROVIDER", "mock")
os.environ.setdefault("ML_SERVICE_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite://")
# Cost 4 instead of 12: same algorithm, ~30x faster tests.
os.environ.setdefault("BCRYPT_ROUNDS", "4")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.deps import reset_rate_limits  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    """A standalone session bound to a fresh in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(session: Session) -> Generator[TestClient, None, None]:
    """A TestClient wired to the fixture session, so assertions can inspect rows."""
    from app.main import create_app

    settings.database_url = "sqlite://"
    app = create_app()

    def _override_get_db():
        try:
            yield session
        finally:
            pass  # the fixture owns the session lifecycle

    app.dependency_overrides[get_db] = _override_get_db
    reset_rate_limits()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """Register a user and return bearer headers for them."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "farmer@example.com",
            "password": "Sunflower2026",
            "full_name": "Farmer One",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_user_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "other@example.com",
            "password": "Sunflower2026",
            "full_name": "Farmer Two",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def seeded(session: Session) -> Session:
    """Session with commodity/market reference data loaded from the SQL seeds."""
    from app.services.seed_service import seed_reference_data

    seed_reference_data(session)
    return session


@pytest.fixture()
def farm(client: TestClient, auth_headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/v1/farms",
        headers=auth_headers,
        json={
            "name": "Main Farm",
            "district": "Lahore",
            "latitude": 31.5204,
            "longitude": 74.3587,
            "total_area_acres": 12.5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def temp_report_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="agripredict-reports-"))
    monkeypatch.setattr(settings, "report_storage_dir", directory)
    return directory
