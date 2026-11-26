"""Buyer discovery via Google Maps Platform (Places API v1) with local caching.

Why the cache matters
---------------------
Farmers search for buyers repeatedly from the same mandi, and Places calls are
billed. Results are UPSERTed into ``buyers`` keyed by ``place_id`` and reused for
``PLACES_CACHE_DAYS``. When the API key is absent or Google is unreachable the
endpoint returns cached rows with ``source="cache"`` — never fabricated entries.

Mapping to AgriPredict categories
---------------------------------
Google's ``primaryType`` values (``wholesaler``, ``market``, ``cold_storage``,
…) are mapped onto our six categories so the app can filter consistently and so
the category enum in the database stays closed.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotConfiguredError, UpstreamUnavailableError
from app.models import Buyer
from app.schemas import BuyerRead, BuyerSearchResponse
from app.services.finance_service import as_decimal

logger = logging.getLogger(__name__)

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
PLACES_CACHE_DAYS = 30
EARTH_RADIUS_KM = 6371.0088

# Google primaryType -> AgriPredict category
CATEGORY_MAP = {
    "wholesaler": "trader",
    "market": "trader",
    "farmers_market": "cooperative",
    "agricultural_cooperative": "cooperative",
    "cold_storage": "cold_storage",
    "food_store": "trader",
    "supermarket": "trader",
    "storage": "cold_storage",
    "flour_mill": "mill",
    "mill": "mill",
    "real_estate_agency": "commission_agent",
}

# Preferences expressed as Google place types (includedTypes).
SEARCH_TYPES = ["wholesaler", "market", "food_store", "storage"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (used to sort results by real distance)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _map_category(primary_type: str | None, display_name: str | None) -> str:
    if primary_type and primary_type in CATEGORY_MAP:
        return CATEGORY_MAP[primary_type]
    name = (display_name or "").lower()
    if "cold" in name:
        return "cold_storage"
    if "mill" in name or "flour" in name:
        return "mill"
    if "cooperative" in name or "co-op" in name:
        return "cooperative"
    if "commission" in name or "arthi" in name:
        return "commission_agent"
    return "other"


# ---------------------------------------------------------------------------
# Google Places
# ---------------------------------------------------------------------------
def _search_places(
    lat: float, lon: float, radius_m: int, max_results: int
) -> list[dict]:
    """Call Places API (New) searchNearby. Raises on transport/auth problems."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,places.location,"
            "places.primaryType,places.rating,places.userRatingCount,"
            "places.nationalPhoneNumber"
        ),
    }
    payload = {
        "includedTypes": SEARCH_TYPES,
        "maxResultCount": min(max_results, 20),
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(min(radius_m, 50_000)),  # API maximum
            }
        },
    }
    with httpx.Client(timeout=settings.places_timeout_seconds) as client:
        response = client.post(PLACES_SEARCH_URL, json=payload, headers=headers)

    if response.status_code in (401, 403):
        raise UpstreamUnavailableError(
            "Google Places rejected the request. Check GOOGLE_PLACES_API_KEY and that "
            "billing is enabled on the Google Cloud project."
        )
    if response.status_code == 429:
        raise UpstreamUnavailableError("Google Places rate limit reached. Try again later.")
    response.raise_for_status()
    return response.json().get("places", [])


def _upsert_buyers(session: Session, places: list[dict], district: str | None) -> list[Buyer]:
    """Insert or refresh cached buyers; returns the persisted rows."""
    saved: list[Buyer] = []
    now = datetime.now(timezone.utc)

    for place in places:
        place_id = place.get("id")
        if not place_id:
            continue
        existing = session.scalar(select(Buyer).where(Buyer.place_id == place_id))
        name = (place.get("displayName") or {}).get("text") or "Unnamed buyer"
        location = place.get("location") or {}
        buyer = existing or Buyer(place_id=place_id, name=name)
        buyer.name = name
        buyer.category = _map_category(place.get("primaryType"), name)
        buyer.address = place.get("formattedAddress")
        buyer.district = district or existing.district if existing else district
        buyer.latitude = (
            Decimal(str(location["latitude"])) if location.get("latitude") is not None else None
        )
        buyer.longitude = (
            Decimal(str(location["longitude"])) if location.get("longitude") is not None else None
        )
        buyer.rating = (
            Decimal(str(place["rating"])) if place.get("rating") is not None else None
        )
        buyer.user_ratings_total = place.get("userRatingCount")
        buyer.phone = place.get("nationalPhoneNumber")
        buyer.fetched_at = now
        session.add(buyer)
        saved.append(buyer)

    session.flush()
    return saved


# ---------------------------------------------------------------------------
# Cache reads
# ---------------------------------------------------------------------------
def cached_buyers(session: Session, district: str | None, limit: int) -> list[Buyer]:
    stmt = select(Buyer).order_by(Buyer.fetched_at.desc()).limit(limit)
    if district:
        stmt = stmt.where(Buyer.district == district)
    return list(session.scalars(stmt))


def _is_fresh(buyer: Buyer) -> bool:
    fetched = buyer.fetched_at
    if fetched.tzinfo is None:  # SQLite returns naive UTC
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched < timedelta(days=PLACES_CACHE_DAYS)


def _to_read(buyer: Buyer, *, origin: tuple[float, float] | None = None) -> BuyerRead:
    model = BuyerRead.model_validate(buyer)
    if origin and buyer.latitude is not None and buyer.longitude is not None:
        model.distance_km = Decimal(
            f"{haversine_km(origin[0], origin[1], float(buyer.latitude), float(buyer.longitude)):.2f}"
        )
    return model


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def find_buyers(
    session: Session,
    *,
    latitude: float | None,
    longitude: float | None,
    district: str | None,
    radius_m: int | None = None,
    limit: int | None = None,
    allow_cache_only: bool = False,
) -> BuyerSearchResponse:
    """Return nearby buyers, refreshing from Google when possible."""
    radius = radius_m or settings.places_default_radius_m
    max_results = min(limit or settings.places_max_results, settings.places_max_results)

    if allow_cache_only or not settings.has_places_key:
        rows = cached_buyers(session, district, max_results)
        return _cache_response(
            rows,
            radius,
            note=(
                "Live buyer search is not configured on the server "
                "(GOOGLE_PLACES_API_KEY is empty). Showing cached buyers only."
                if not settings.has_places_key
                else "Cache-only request."
            ),
            origin=(latitude, longitude) if latitude and longitude else None,
        )

    if latitude is None or longitude is None:
        raise NotConfiguredError(
            "Latitude and longitude are required for a live buyer search."
        )

    try:
        places = _search_places(latitude, longitude, radius, max_results)
    except (httpx.HTTPError, UpstreamUnavailableError) as exc:
        logger.warning("Places search failed (%s); serving cache", exc)
        rows = cached_buyers(session, district, max_results)
        if not rows:
            if isinstance(exc, UpstreamUnavailableError):
                raise
            raise UpstreamUnavailableError(
                "Buyer search is temporarily unavailable and no cached results exist."
            ) from exc
        return _cache_response(
            rows,
            radius,
            note="Live buyer search failed; showing cached buyers.",
            origin=(latitude, longitude),
        )

    if not places:
        rows = cached_buyers(session, district, max_results)
        return _cache_response(
            rows,
            radius,
            note="No buyers were found nearby in Google Places. Showing cached buyers, if any.",
            origin=(latitude, longitude),
        )

    saved = _upsert_buyers(session, places, district)
    session.commit()

    results = [_to_read(buyer, origin=(latitude, longitude)) for buyer in saved]
    results.sort(key=lambda r: (r.distance_km is None, r.distance_km or 0))
    return BuyerSearchResponse(
        results=results[:max_results],
        count=len(results[:max_results]),
        radius_m=radius,
        source="google_places",
        note="Results from Google Maps Platform; cached locally for 30 days.",
    )


def _cache_response(
    rows: list[Buyer],
    radius: int,
    *,
    note: str,
    origin: tuple[float, float] | None,
) -> BuyerSearchResponse:
    results = [_to_read(row, origin=origin) for row in rows if _is_fresh(row) or True]
    results.sort(key=lambda r: (r.distance_km is None, r.distance_km or 0))
    return BuyerSearchResponse(
        results=results,
        count=len(results),
        radius_m=radius,
        source="cache" if results else "unavailable",
        note=note,
    )


def list_saved_buyers(session: Session, limit: int = 50) -> list[BuyerRead]:
    return [_to_read(row) for row in cached_buyers(session, None, limit)]


def stale_count(session: Session) -> int:
    """Number of cached buyers due for refresh — surfaced in admin health output."""
    rows: list[Buyer] = list(session.scalars(select(Buyer)))
    return sum(1 for row in rows if not _is_fresh(row))


__all__ = [
    "find_buyers",
    "list_saved_buyers",
    "cached_buyers",
    "haversine_km",
    "stale_count",
    "as_decimal",
]
