"""Weather integration: OpenWeatherMap primary, Open-Meteo keyless fallback.

Provider selection (``WEATHER_PROVIDER``):

* ``openweathermap`` — used when ``OPENWEATHER_API_KEY`` is set.
* ``open-meteo``     — no key required; automatically used when the OWM key is
                       missing, so a fresh clone still demonstrates the feature.
* ``mock``           — deterministic fixture data for tests, clearly labelled
                       ``is_live=False`` so the UI can say it is simulated.

Every result carries ``provider`` and ``is_live``. The app must never present
fallback or mock data as a live observation — that is an honesty requirement, not
a cosmetic one.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.core.config import settings
from app.core.exceptions import UpstreamUnavailableError
from app.schemas import WeatherBundle, WeatherCurrent, WeatherForecastDay

logger = logging.getLogger(__name__)

OWM_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(f"{float(value):.2f}")


def resolve_provider() -> str:
    """Decide which provider to use given the configured credentials."""
    if settings.weather_provider == "mock":
        return "mock"
    if settings.weather_provider == "open-meteo":
        return "open-meteo"
    # openweathermap requested
    return "openweathermap" if settings.has_weather_key else "open-meteo"


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------
def _fetch_openweathermap(lat: float, lon: float) -> WeatherBundle:
    params = {"lat": lat, "lon": lon, "appid": settings.openweather_api_key, "units": "metric"}
    with httpx.Client(timeout=settings.weather_timeout_seconds) as client:
        current_response = client.get(OWM_CURRENT_URL, params=params)
        if current_response.status_code == 401:
            raise UpstreamUnavailableError(
                "OpenWeatherMap rejected the API key. Check OPENWEATHER_API_KEY."
            )
        current_response.raise_for_status()
        current = current_response.json()

        forecast_days: list[WeatherForecastDay] = []
        try:
            forecast_response = client.get(OWM_FORECAST_URL, params=params)
            forecast_response.raise_for_status()
            # OWM's 5-day/3-hour endpoint: aggregate the 8 slots per calendar day.
            daily: dict[date, dict[str, float]] = {}
            for slot in forecast_response.json().get("list", []):
                day = datetime.fromtimestamp(slot["dt"], tz=timezone.utc).date()
                bucket = daily.setdefault(day, {"min": 1e9, "max": -1e9, "rain": 0.0})
                bucket["min"] = min(bucket["min"], slot["main"]["temp_min"])
                bucket["max"] = max(bucket["max"], slot["main"]["temp_max"])
                bucket["rain"] += float(slot.get("rain", {}).get("3h", 0.0))
            conditions = {
                datetime.fromtimestamp(s["dt"], tz=timezone.utc).date(): s["weather"][0]["description"]
                for s in forecast_response.json().get("list", [])
            }
            forecast_days = [
                WeatherForecastDay(
                    day=day,
                    temp_min_c=_dec(bucket["min"]),
                    temp_max_c=_dec(bucket["max"]),
                    precipitation_mm=_dec(bucket["rain"]),
                    condition=conditions.get(day),
                )
                for day, bucket in sorted(daily.items())
            ]
        except httpx.HTTPError as exc:  # current conditions still succeed
            logger.warning("Weather forecast unavailable: %s", exc)

    main = current.get("main", {})
    wind = current.get("wind", {})
    return WeatherBundle(
        current=WeatherCurrent(
            farm_id=0,
            observed_at=datetime.now(timezone.utc),
            temperature_c=_dec(main.get("temp")),
            humidity_pct=_dec(main.get("humidity")),
            wind_kph=_dec((wind.get("speed") or 0) * 3.6),
            precipitation_mm=_dec(current.get("rain", {}).get("1h", 0.0)),
            condition=(current.get("weather") or [{}])[0].get("description"),
            provider="openweathermap",
            is_live=True,
        ),
        forecast=forecast_days,
        provider="openweathermap",
        is_live=True,
    )


def _fetch_open_meteo(lat: float, lon: float) -> WeatherBundle:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code",
        "forecast_days": 7,
        "timezone": "auto",
    }
    with httpx.Client(timeout=settings.weather_timeout_seconds) as client:
        response = client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        body = response.json()

    current = body.get("current", {})
    daily = body.get("daily", {})
    days = daily.get("time", [])

    forecast_days = [
        WeatherForecastDay(
            day=date.fromisoformat(days[i]),
            temp_min_c=_dec(daily["temperature_2m_min"][i]),
            temp_max_c=_dec(daily["temperature_2m_max"][i]),
            precipitation_mm=_dec(daily["precipitation_sum"][i]),
            condition=_wmo_condition(daily["weather_code"][i]),
        )
        for i in range(len(days))
    ]

    return WeatherBundle(
        current=WeatherCurrent(
            farm_id=0,
            observed_at=datetime.now(timezone.utc),
            temperature_c=_dec(current.get("temperature_2m")),
            humidity_pct=_dec(current.get("relative_humidity_2m")),
            wind_kph=_dec(current.get("wind_speed_10m")),
            precipitation_mm=_dec(current.get("precipitation")),
            condition=_wmo_condition(current.get("weather_code", 0)),
            provider="open-meteo",
            is_live=True,
        ),
        forecast=forecast_days,
        provider="open-meteo",
        is_live=True,
    )


WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snowfall",
    73: "moderate snowfall",
    75: "heavy snowfall",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _wmo_condition(code: int | None) -> str:
    return WMO_CODES.get(int(code or 0), "unknown")


def mock_weather(lat: float, lon: float, farm_id: int = 0) -> WeatherBundle:
    """Deterministic fixture derived from coordinates.

    Used by tests and by ``WEATHER_PROVIDER=mock``. Values are physically
    plausible and stable for a given location, so UI snapshots do not flake.
    """
    seed = abs(int(lat * 1000) + int(lon * 1000))
    base_temp = 18 + (seed % 17)  # 18–34 °C
    today = date.today()
    return WeatherBundle(
        current=WeatherCurrent(
            farm_id=farm_id,
            observed_at=datetime.now(timezone.utc),
            temperature_c=Decimal(f"{base_temp}.00"),
            humidity_pct=Decimal(f"{40 + seed % 40}.00"),
            wind_kph=Decimal(f"{5 + seed % 15}.00"),
            precipitation_mm=Decimal("0.00"),
            condition="clear sky (simulated)",
            provider="mock",
            is_live=False,
            note="Simulated data: no live weather provider is configured.",
        ),
        forecast=[
            WeatherForecastDay(
                day=today + timedelta(days=offset),
                temp_min_c=Decimal(f"{base_temp - 7 + offset % 3}.00"),
                temp_max_c=Decimal(f"{base_temp + 3 + offset % 4}.00"),
                precipitation_mm=Decimal(f"{(seed + offset) % 5}.00"),
                condition="partly cloudy (simulated)",
            )
            for offset in range(1, 8)
        ],
        provider="mock",
        is_live=False,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def get_weather(lat: float | None, lon: float | None, farm_id: int = 0) -> WeatherBundle:
    """Fetch current weather and a 7-day outlook for a location.

    Missing coordinates are a client error (422 at the API layer) rather than a
    guess at the user's position.
    """
    if lat is None or lon is None:
        raise UpstreamUnavailableError(
            "This farm has no coordinates. Add latitude/longitude to enable weather."
        )

    provider = resolve_provider()
    try:
        if provider == "mock":
            bundle = mock_weather(float(lat), float(lon), farm_id)
        elif provider == "openweathermap":
            bundle = _fetch_openweathermap(float(lat), float(lon))
        else:
            bundle = _fetch_open_meteo(float(lat), float(lon))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Weather provider %s failed: %s", provider, exc)
        # Degrade to the keyless provider when the paid one is unreachable.
        if provider == "openweathermap":
            try:
                bundle = _fetch_open_meteo(float(lat), float(lon))
            except (httpx.HTTPError, ValueError) as fallback_exc:
                logger.warning("Open-Meteo fallback also failed: %s", fallback_exc)
                raise UpstreamUnavailableError(
                    "Weather data is temporarily unavailable. Please try again later."
                ) from fallback_exc
            bundle.current.note = "OpenWeatherMap failed; using the Open-Meteo fallback."
        else:
            raise UpstreamUnavailableError(
                "Weather data is temporarily unavailable. Please try again later."
            ) from exc

    # Attach the farm id (the providers build a placeholder) so the response is
    # unambiguous when a client refreshes several farms.
    bundle.current.farm_id = farm_id
    return bundle
