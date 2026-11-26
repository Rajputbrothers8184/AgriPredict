"""Farms, crop cycles, expenses, sales and finance-rollup endpoints."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Commodity, Market


def _seed(session: Session) -> tuple[int, int]:
    from app.services.seed_service import seed_reference_data

    seed_reference_data(session)
    commodity = session.query(Commodity).filter_by(slug="wheat").one()
    market = session.query(Market).filter_by(slug="lahore-sabzi-mandi").one()
    return commodity.id, market.id


@pytest.fixture()
def commodity_market(seeded: Session) -> tuple[int, int]:
    return _seed(seeded)


def _cycle(client: TestClient, headers: dict, farm_id: int, commodity_id: int, **overrides):
    payload = {
        "farm_id": farm_id,
        "commodity_id": commodity_id,
        "season": "rabi",
        "area_acres": 5,
        "sowing_date": "2026-11-01",
        "expected_harvest_date": "2027-04-15",
        "status": "active",
    }
    payload.update(overrides)
    return client.post("/api/v1/crop-cycles", headers=headers, json=payload)


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------
def test_create_and_list_farm(client: TestClient, auth_headers: dict, farm: dict):
    assert farm["name"] == "Main Farm"
    listing = client.get("/api/v1/farms", headers=auth_headers)
    assert listing.status_code == 200
    assert [f["id"] for f in listing.json()] == [farm["id"]]


def test_farm_requires_both_coordinates(client: TestClient, auth_headers: dict):
    response = client.post(
        "/api/v1/farms",
        headers=auth_headers,
        json={"name": "Broken", "district": "Lahore", "latitude": 31.5},
    )
    assert response.status_code == 422


def test_farm_coordinates_are_range_checked(client: TestClient, auth_headers: dict):
    response = client.post(
        "/api/v1/farms",
        headers=auth_headers,
        json={"name": "Off-planet", "district": "Lahore", "latitude": 120, "longitude": 74},
    )
    assert response.status_code == 422


def test_other_user_cannot_read_my_farm(
    client: TestClient, farm: dict, other_user_headers: dict
):
    response = client.get(f"/api/v1/farms/{farm['id']}", headers=other_user_headers)
    assert response.status_code == 404  # not 403: do not confirm existence


def test_other_user_cannot_delete_my_farm(
    client: TestClient, farm: dict, other_user_headers: dict
):
    response = client.delete(f"/api/v1/farms/{farm['id']}", headers=other_user_headers)
    assert response.status_code == 404
    assert client.get(f"/api/v1/farms/{farm['id']}", headers=other_user_headers).status_code == 404


def test_update_farm(client: TestClient, auth_headers: dict, farm: dict):
    response = client.patch(
        f"/api/v1/farms/{farm['id']}", headers=auth_headers, json={"name": "North Field"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "North Field"


def test_delete_farm(client: TestClient, auth_headers: dict, farm: dict):
    assert client.delete(f"/api/v1/farms/{farm['id']}", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/farms", headers=auth_headers).json() == []


# ---------------------------------------------------------------------------
# Crop cycles
# ---------------------------------------------------------------------------
def test_create_cycle_and_read_detail_with_finance(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    created = _cycle(client, auth_headers, farm["id"], commodity_id)
    assert created.status_code == 201, created.text

    cycle_id = created.json()["id"]
    client.post(
        f"/api/v1/crop-cycles/{cycle_id}/expenses",
        headers=auth_headers,
        json={"category": "fertilizer", "amount_pkr": 42500, "expense_date": "2026-11-02"},
    )
    client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={
            "quantity_kg": 2000,
            "unit_price_pkr": 3900,
            "sale_date": "2026-11-20",
            "buyer_name": "Local trader",
        },
    )

    detail = client.get(f"/api/v1/crop-cycles/{cycle_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["commodity"]["slug"] == "wheat"
    assert body["finance"]["cost_pkr"] == "42500.00"
    assert body["finance"]["revenue_pkr"] == "195000.00"
    assert body["finance"]["profit_pkr"] == "152500.00"


def test_cycle_cannot_reference_another_users_farm(
    client: TestClient, farm: dict, other_user_headers: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    response = _cycle(client, other_user_headers, farm["id"], commodity_id)
    assert response.status_code == 404


def test_cycle_rejects_unknown_commodity(
    client: TestClient, auth_headers: dict, farm: dict, seeded: Session
):
    response = _cycle(client, auth_headers, farm["id"], 999_999)
    assert response.status_code == 422


def test_cycle_rejects_harvest_before_sowing(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    response = _cycle(
        client,
        auth_headers,
        farm["id"],
        commodity_id,
        sowing_date="2026-11-10",
        expected_harvest_date="2026-11-01",
    )
    assert response.status_code == 422


def test_cycle_rejects_zero_area(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    assert _cycle(client, auth_headers, farm["id"], commodity_id, area_acres=0).status_code == 422


def test_cycle_status_filter(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    _cycle(client, auth_headers, farm["id"], commodity_id, status="active")
    _cycle(client, auth_headers, farm["id"], commodity_id, status="harvested")

    active = client.get(
        "/api/v1/crop-cycles?status=active", headers=auth_headers
    ).json()
    assert len(active) == 1 and active[0]["status"] == "active"

    invalid = client.get("/api/v1/crop-cycles?status=banana", headers=auth_headers)
    assert invalid.status_code == 422


def test_other_user_cannot_read_my_cycle(
    client: TestClient, auth_headers: dict, farm: dict, other_user_headers: dict,
    commodity_market: tuple[int, int],
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    assert (
        client.get(f"/api/v1/crop-cycles/{cycle_id}", headers=other_user_headers).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
def test_expense_amount_cannot_be_negative(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/expenses",
        headers=auth_headers,
        json={"category": "seeds", "amount_pkr": -1, "expense_date": "2026-11-01"},
    )
    assert response.status_code == 422


def test_expense_category_is_validated(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/expenses",
        headers=auth_headers,
        json={"category": "bribes", "amount_pkr": 100, "expense_date": "2026-11-01"},
    )
    assert response.status_code == 422


def test_expense_list_and_delete(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    created = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/expenses",
        headers=auth_headers,
        json={"category": "labour", "amount_pkr": 15000, "expense_date": "2026-11-04"},
    ).json()

    listing = client.get(f"/api/v1/crop-cycles/{cycle_id}/expenses", headers=auth_headers)
    assert listing.status_code == 200 and len(listing.json()) == 1

    delete = client.delete(
        f"/api/v1/crop-cycles/{cycle_id}/expenses/{created['id']}", headers=auth_headers
    )
    assert delete.status_code == 200
    assert client.get(f"/api/v1/crop-cycles/{cycle_id}/expenses", headers=auth_headers).json() == []


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
def test_sale_total_is_derived_server_side(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, market_id = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]

    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={
            "quantity_kg": 2000,
            "unit_price_pkr": 3900,
            "sale_date": "2026-11-20",
            "market_id": market_id,
            # A malicious/naive client cannot set the total:
            "total_amount_pkr": 1,
        },
    )
    # Unknown fields are rejected outright — the client must not send a total.
    assert response.status_code == 422

    clean = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={
            "quantity_kg": 2000,
            "unit_price_pkr": 3900,
            "sale_date": "2026-11-20",
            "market_id": market_id,
        },
    )
    assert clean.status_code == 201
    assert clean.json()["total_amount_pkr"] == "195000.00"


def test_sale_total_is_recomputed_on_update(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    sale = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={"quantity_kg": 400, "unit_price_pkr": 3900, "sale_date": "2026-11-20"},
    ).json()
    assert sale["total_amount_pkr"] == "39000.00"

    updated = client.patch(
        f"/api/v1/crop-cycles/{cycle_id}/sales/{sale['id']}",
        headers=auth_headers,
        json={"quantity_kg": 800},
    ).json()
    assert updated["total_amount_pkr"] == "78000.00"


def test_sale_date_cannot_be_in_the_future(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={"quantity_kg": 400, "unit_price_pkr": 3900, "sale_date": tomorrow},
    )
    assert response.status_code == 422


def test_sale_rejects_zero_quantity(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    cycle_id = _cycle(client, auth_headers, farm["id"], commodity_id).json()["id"]
    response = client.post(
        f"/api/v1/crop-cycles/{cycle_id}/sales",
        headers=auth_headers,
        json={"quantity_kg": 0, "unit_price_pkr": 3900, "sale_date": "2026-11-20"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Finance rollups
# ---------------------------------------------------------------------------
def test_finance_summary_across_cycles(
    client: TestClient, auth_headers: dict, farm: dict, commodity_market: tuple[int, int]
):
    commodity_id, _ = commodity_market
    for season in ("rabi", "kharif"):
        cycle_id = _cycle(
            client, auth_headers, farm["id"], commodity_id, season=season
        ).json()["id"]
        client.post(
            f"/api/v1/crop-cycles/{cycle_id}/expenses",
            headers=auth_headers,
            json={"category": "seeds", "amount_pkr": 10000, "expense_date": "2026-11-02"},
        )
        client.post(
            f"/api/v1/crop-cycles/{cycle_id}/sales",
            headers=auth_headers,
            json={"quantity_kg": 2000, "unit_price_pkr": 3900, "sale_date": "2026-11-20"},
        )

    summary = client.get("/api/v1/finance/summary", headers=auth_headers).json()
    assert summary["lifetime_cost_pkr"] == "20000.00"
    assert summary["lifetime_revenue_pkr"] == "390000.00"
    assert summary["lifetime_profit_pkr"] == "370000.00"
    assert len(summary["seasons"]) == 2
    assert summary["expense_breakdown"][0]["category"] == "seeds"


def test_finance_summary_is_empty_for_new_user(client: TestClient, auth_headers: dict):
    summary = client.get("/api/v1/finance/summary", headers=auth_headers).json()
    assert summary["lifetime_revenue_pkr"] == "0.00"
    assert summary["margin_pct"] is None
    assert summary["seasons"] == []


def test_finance_summary_requires_auth(client: TestClient):
    assert client.get("/api/v1/finance/summary").status_code == 401
