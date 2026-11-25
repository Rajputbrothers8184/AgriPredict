"""Forecast, weather, buyer, report and health endpoints.

External services are mocked with ``httpx.MockTransport`` semantics by patching
the service-level functions, so these tests are fast, deterministic and never
touch the network — while still exercising the real fallback logic.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Buyer, Commodity, Market, PriceRecord
from app.services.seed_service import seed_reference_data


def _seed_prices(session: Session, days: int = 60) -> tuple[Commodity, Market]:
    seed_reference_data(session)
    commodity = session.query(Commodity).filter_by(slug="wheat").one()
    market = session.query(Market).filter_by(slug="lahore-sabzi-mandi").one()
    start = date(2026, 9, 1)
    for offset in range(days):
        session.add(
            PriceRecord(
                commodity_id=commodity.id,
                market_id=market.id,
                price_date=start + timedelta(days=offset),
                min_price_pkr=3800 + offset,
                max_price_pkr=4000 + offset,
                avg_price_pkr=3900 + (offset % 7) * 10,
                source="synthetic_fixture",  # generated data, honestly labelled
            )
        )
    session.commit()
    return commodity, market


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------
def test_commodities_are_public(client: TestClient, seeded: Session):
    response = client.get("/api/v1/markets/commodities")
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.json()}
    assert {"wheat", "cotton", "potato"} <= slugs
    wheat = next(row for row in response.json() if row["slug"] == "wheat")
    assert wheat["name_ur"] == "گندم"


def test_markets_list(client: TestClient, seeded: Session):
    response = client.get("/api/v1/markets/list")
    assert response.status_code == 200
    assert any(m["slug"] == "lahore-sabzi-mandi" for m in response.json())


def test_price_history_returns_labelled_source(
    client: TestClient, session: Session, auth_headers: dict
):
    _seed_prices(session)
    response = client.get(
        "/api/v1/markets/history/wheat/lahore-sabzi-mandi?days=30", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unit"] == "PKR/40kg"
    # Inclusive date window: 30 days back from the newest quote spans 31 days.
    assert body["count"] == 31
    assert all(point["source"] == "synthetic_fixture" for point in body["points"])


def test_price_history_unknown_commodity_is_404(
    client: TestClient, seeded: Session, auth_headers: dict
):
    response = client.get(
        "/api/v1/markets/history/unicorn/lahore-sabzi-mandi", headers=auth_headers
    )
    assert response.status_code == 404


def test_market_comparison_ranks_markets(
    client: TestClient, session: Session, auth_headers: dict
):
    commodity, lahore = _seed_prices(session, days=30)
    multan = session.query(Market).filter_by(slug="multan-mandi").one()
    for offset in range(30):
        session.add(
            PriceRecord(
                commodity_id=commodity.id,
                market_id=multan.id,
                price_date=date(2026, 9, 1) + timedelta(days=offset),
                avg_price_pkr=4100,
                source="synthetic_fixture",
            )
        )
    session.commit()

    response = client.get("/api/v1/markets/compare/wheat", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["best_market_slug"] == "multan-mandi"
    assert body["rows"][0]["latest_price_pkr"] == "4100.00"


# ---------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------
def test_forecast_falls_back_and_says_so(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    _seed_prices(session)
    monkeypatch.setattr(settings, "ml_service_enabled", False)

    response = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi?horizon=7", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["horizon_days"] == 7
    assert len(body["points"]) == 7
    assert body["is_fallback"] is True
    assert body["model_name"] == "seasonal_naive"
    assert body["mae"] is not None and body["rmse"] is not None
    assert "fallback" in body["disclaimer"].lower()


@pytest.mark.parametrize("horizon", [7, 30])
def test_forecast_horizons(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch, horizon: int
):
    _seed_prices(session, days=90)
    monkeypatch.setattr(settings, "ml_service_enabled", False)
    response = client.get(
        f"/api/v1/forecasts/wheat/lahore-sabzi-mandi?horizon={horizon}&refresh=true",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["points"]) == horizon


def test_forecast_rejects_unsupported_horizon(
    client: TestClient, session: Session, auth_headers: dict
):
    _seed_prices(session)
    response = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi?horizon=14", headers=auth_headers)
    assert response.status_code == 422


def test_forecast_requires_enough_history(
    client: TestClient, session: Session, auth_headers: dict
):
    _seed_prices(session, days=5)
    response = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi", headers=auth_headers)
    assert response.status_code == 422
    assert "Not enough price history" in response.json()["error"]["message"]


def test_forecast_uses_ml_service_when_available(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch
):
    _seed_prices(session)
    from app.services import ml_client

    class FakeResult:
        model_name = "xgboost"
        issued_on = date(2026, 10, 30)
        mae = __import__("decimal").Decimal("41.20")
        rmse = __import__("decimal").Decimal("58.70")
        metrics = {"features": 12}
        points = [
            {
                "target_date": date(2026, 11, 1) + timedelta(days=i),
                "predicted_price_pkr": __import__("decimal").Decimal("3950.00"),
                "lower_bound_pkr": __import__("decimal").Decimal("3900.00"),
                "upper_bound_pkr": __import__("decimal").Decimal("4000.00"),
            }
            for i in range(7)
        ]

    monkeypatch.setattr(ml_client, "is_ml_service_configured", lambda: True)
    monkeypatch.setattr(ml_client, "request_forecast", lambda **_kwargs: FakeResult())

    response = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi?horizon=7", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "xgboost"
    assert body["is_fallback"] is False
    assert body["metrics"] == {"features": 12}


def test_forecast_is_cached(client: TestClient, session: Session, auth_headers: dict, monkeypatch):
    _seed_prices(session)
    monkeypatch.setattr(settings, "ml_service_enabled", False)
    first = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi", headers=auth_headers).json()
    second = client.get("/api/v1/forecasts/wheat/lahore-sabzi-mandi", headers=auth_headers).json()
    assert first["id"] == second["id"]  # served from cache, not regenerated


def test_latest_forecast_404_before_any_run(
    client: TestClient, session: Session, auth_headers: dict
):
    _seed_prices(session)
    response = client.get("/api/v1/forecasts/latest/wheat/lahore-sabzi-mandi", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def test_weather_for_farm_uses_mock_provider(
    client: TestClient, auth_headers: dict, farm: dict
):
    response = client.get(f"/api/v1/weather/{farm['id']}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["is_live"] is False           # never claim simulated data is live
    assert len(body["forecast"]) == 7
    assert "simulated" in body["current"]["condition"]


def test_weather_requires_coordinates(client: TestClient, auth_headers: dict):
    created = client.post(
        "/api/v1/farms",
        headers=auth_headers,
        json={"name": "No GPS", "district": "Lahore"},
    ).json()
    response = client.get(f"/api/v1/weather/{created['id']}", headers=auth_headers)
    assert response.status_code == 422
    assert "latitude" in response.json()["error"]["message"].lower()


def test_weather_upstream_failure_returns_503(
    client: TestClient, auth_headers: dict, farm: dict, monkeypatch
):
    from app.core.exceptions import UpstreamUnavailableError
    from app.services import weather_service

    def _boom(*_args, **_kwargs):
        raise UpstreamUnavailableError("Weather provider unreachable.")

    monkeypatch.setattr(weather_service, "get_weather", _boom)
    response = client.get(f"/api/v1/weather/{farm['id']}?refresh=true", headers=auth_headers)
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Buyers
# ---------------------------------------------------------------------------
def test_buyers_without_api_key_returns_cache_and_explains(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(settings, "google_places_api_key", "")
    session.add(Buyer(place_id="ChIJtest1", name="Lahore Grain Trader", district="Lahore"))
    session.commit()

    response = client.get("/api/v1/buyers?district=Lahore", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["count"] == 1
    assert "not configured" in body["note"]


def test_buyers_without_key_and_without_cache_is_empty_not_fake(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(settings, "google_places_api_key", "")
    response = client.get("/api/v1/buyers", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["source"] == "unavailable"


def test_buyers_from_google_are_cached_with_distance(
    client: TestClient, session: Session, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(settings, "google_places_api_key", "fake-key")
    from app.services import buyer_service

    monkeypatch.setattr(
        buyer_service,
        "_search_places",
        lambda *_args, **_kwargs: [
            {
                "id": "ChIJnear",
                "displayName": {"text": "Nearby Mandi Trader"},
                "formattedAddress": "Multan Road, Lahore",
                "location": {"latitude": 31.53, "longitude": 74.36},
                "primaryType": "wholesaler",
                "rating": 4.4,
                "userRatingCount": 51,
            },
            {
                "id": "ChIJfar",
                "displayName": {"text": "Far Cold Store"},
                "location": {"latitude": 31.70, "longitude": 74.50},
                "primaryType": "storage",
            },
        ],
    )

    response = client.get(
        "/api/v1/buyers?latitude=31.5204&longitude=74.3587", headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "google_places"
    assert [r["name"] for r in body["results"]][0] == "Nearby Mandi Trader"
    assert body["results"][0]["category"] == "trader"
    assert body["results"][1]["category"] == "cold_storage"
    assert body["results"][0]["distance_km"] is not None
    # Persisted for offline use.
    assert session.query(Buyer).count() == 2


def test_buyers_near_farm_uses_farm_coordinates(
    client: TestClient, session: Session, auth_headers: dict, farm: dict, monkeypatch
):
    monkeypatch.setattr(settings, "google_places_api_key", "")
    session.add(Buyer(place_id="ChIJx", name="Local Buyer", district="Lahore"))
    session.commit()
    response = client.get(f"/api/v1/buyers/farm/{farm['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["count"] == 1


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def _populate(client: TestClient, session: Session, headers: dict, farm: dict) -> int:
    _seed_prices(session)
    commodity = session.query(Commodity).filter_by(slug="wheat").one()
    cycle = client.post(
        "/api/v1/crop-cycles",
        headers=headers,
        json={
            "farm_id": farm["id"],
            "commodity_id": commodity.id,
            "season": "rabi",
            "area_acres": 5,
            "sowing_date": "2026-11-01",
        },
    ).json()
    client.post(
        f"/api/v1/crop-cycles/{cycle['id']}/expenses",
        headers=headers,
        json={"category": "fertilizer", "amount_pkr": 42500, "expense_date": "2026-11-02"},
    )
    client.post(
        f"/api/v1/crop-cycles/{cycle['id']}/sales",
        headers=headers,
        json={"quantity_kg": 2000, "unit_price_pkr": 3900, "sale_date": "2026-11-20"},
    )
    return cycle["id"]


def test_generate_pdf_report(
    client: TestClient, session: Session, auth_headers: dict, farm: dict, temp_report_dir
):
    _populate(client, session, auth_headers, farm)
    response = client.post(
        "/api/v1/reports",
        headers=auth_headers,
        json={"report_type": "financial_summary", "file_format": "pdf"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"].endswith(".pdf")
    assert body["size_bytes"] > 1000

    download = client.get(body["download_url"], headers=auth_headers)
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    assert download.headers["content-type"] == "application/pdf"


def test_generate_excel_report(
    client: TestClient, session: Session, auth_headers: dict, farm: dict, temp_report_dir
):
    _populate(client, session, auth_headers, farm)
    response = client.post(
        "/api/v1/reports",
        headers=auth_headers,
        json={"report_type": "financial_summary", "file_format": "xlsx"},
    )
    assert response.status_code == 200
    download = client.get(response.json()["download_url"], headers=auth_headers)
    assert download.content[:2] == b"PK"  # xlsx is a zip container


def test_crop_cycle_report_requires_cycle_id(
    client: TestClient, session: Session, auth_headers: dict, temp_report_dir
):
    response = client.post(
        "/api/v1/reports",
        headers=auth_headers,
        json={"report_type": "crop_cycle", "file_format": "pdf"},
    )
    assert response.status_code == 422


def test_other_user_cannot_download_my_report(
    client: TestClient,
    session: Session,
    auth_headers: dict,
    other_user_headers: dict,
    farm: dict,
    temp_report_dir,
):
    created = client.post(
        "/api/v1/reports",
        headers=auth_headers,
        json={"report_type": "financial_summary", "file_format": "pdf"},
    ).json()
    response = client.get(created["download_url"], headers=other_user_headers)
    assert response.status_code == 404


def test_report_download_rejects_path_traversal(
    client: TestClient, auth_headers: dict, temp_report_dir
):
    from app.core.exceptions import NotFoundError
    from app.services.report_service import resolve_existing

    with pytest.raises(NotFoundError):
        resolve_existing("../../etc/passwd")


# ---------------------------------------------------------------------------
# Health & meta
# ---------------------------------------------------------------------------
def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["ml_service"] in {"ok", "unavailable", "disabled"}


def test_root_identifies_service(client: TestClient):
    body = client.get("/").json()
    assert body["service"] == "AgriPredict"
    assert body["api"] == "/api/v1"


def test_openapi_document_is_valid(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"].startswith("AgriPredict")
    assert "/api/v1/auth/login" in schema["paths"]


def test_security_headers_are_present(client: TestClient):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in response.headers


def test_unknown_route_returns_json_404(client: TestClient):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
