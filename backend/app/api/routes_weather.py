"""Weather endpoints (per-farm current conditions and 7-day outlook)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.schemas import WeatherBundle
from app.services import crop_service, weather_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/{farm_id}", response_model=WeatherBundle, summary="Weather for one farm")
def farm_weather(
    farm_id: int,
    session: DbSession,
    user: CurrentUser,
    refresh: bool = Query(default=False, description="Bypass the snapshot cache"),
) -> WeatherBundle:
    farm = crop_service.get_farm(session, user.id, farm_id)
    if farm.latitude is None or farm.longitude is None:
        raise ValidationError(
            "Add latitude and longitude to this farm to see weather.",
            details={"field": "latitude/longitude", "farm_id": farm_id},
        )

    if not refresh:
        cached = _fresh_snapshot(session, farm_id)
        if cached is not None:
            return cached

    bundle = weather_service.get_weather(
        float(farm.latitude), float(farm.longitude), farm_id=farm_id
    )
    _store_snapshot(session, farm_id, bundle)
    return bundle


@router.get("/current", response_model=WeatherBundle, summary="Weather for arbitrary coordinates")
def weather_at(
    _user: CurrentUser,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> WeatherBundle:
    """Used by the app before a farm with coordinates exists."""
    return weather_service.get_weather(latitude, longitude)


# ---------------------------------------------------------------------------
# Snapshot caching
# ---------------------------------------------------------------------------
def _fresh_snapshot(session, farm_id: int) -> WeatherBundle | None:
    from sqlalchemy import select

    from app.models import WeatherSnapshot

    row = session.scalar(
        select(WeatherSnapshot)
        .where(WeatherSnapshot.farm_id == farm_id)
        .order_by(WeatherSnapshot.observed_at.desc())
        .limit(1)
    )
    if row is None:
        return None

    observed = row.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - observed).total_seconds() / 60
    if age_minutes > settings.weather_cache_minutes:
        return None

    from app.schemas import WeatherCurrent

    return WeatherBundle(
        current=WeatherCurrent(
            farm_id=farm_id,
            observed_at=observed,
            temperature_c=row.temperature_c,
            humidity_pct=row.humidity_pct,
            wind_kph=row.wind_kph,
            precipitation_mm=row.precipitation_mm,
            condition=row.condition,
            provider=row.provider,  # type: ignore[arg-type]
            is_live=row.provider != "mock",
            note="Cached observation.",
        ),
        forecast=[],
        provider=row.provider,  # type: ignore[arg-type]
        is_live=row.provider != "mock",
    )


def _store_snapshot(session, farm_id: int, bundle: WeatherBundle) -> None:
    from app.models import WeatherSnapshot

    current = bundle.current
    session.add(
        WeatherSnapshot(
            farm_id=farm_id,
            observed_at=current.observed_at,
            temperature_c=current.temperature_c,
            humidity_pct=current.humidity_pct,
            wind_kph=current.wind_kph,
            precipitation_mm=current.precipitation_mm,
            condition=current.condition,
            provider=bundle.provider,
            raw_json=json.dumps(
                {
                    "forecast": [
                        {
                            "day": day.day.isoformat(),
                            "min": str(day.temp_min_c),
                            "max": str(day.temp_max_c),
                            "precip": str(day.precipitation_mm),
                        }
                        for day in bundle.forecast
                    ]
                }
            ),
        )
    )
    session.commit()
