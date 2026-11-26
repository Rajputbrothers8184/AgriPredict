"""HTTP client for the separate ML prediction service (``ml/``).

Contract (served by ``ml/inference/service.py``):

    POST {ML_SERVICE_URL}/predict
    {
      "commodity_slug": "wheat",
      "market_slug": "lahore-sabzi-mandi",
      "horizon_days": 7,
      "history": [{"date": "2026-11-01", "price_pkr": 3900.0}, ...],
      "model": "auto"
    }
    → {
      "model_name": "xgboost",
      "issued_on": "2026-11-24",
      "points": [{"target_date": "...", "predicted_price_pkr": 3925.0,
                  "lower_bound_pkr": 3810.0, "upper_bound_pkr": 4040.0}, ...],
      "mae": 41.2, "rmse": 58.7,
      "metrics": {...}
    }

Failure policy: this client never raises into the API layer. It returns
``None`` so the caller can fall back to the local baseline forecaster, because a
degraded forecast is more useful to a farmer than a 500.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MLForecastResult:
    """Normalised ML service response, independent of the wire format."""

    __slots__ = ("model_name", "issued_on", "points", "mae", "rmse", "metrics")

    def __init__(
        self,
        model_name: str,
        issued_on: date,
        points: list[dict],
        mae: Decimal | None,
        rmse: Decimal | None,
        metrics: dict,
    ) -> None:
        self.model_name = model_name
        self.issued_on = issued_on
        self.points = points
        self.mae = mae
        self.rmse = rmse
        self.metrics = metrics


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def is_ml_service_configured() -> bool:
    return settings.ml_service_enabled and bool(settings.ml_service_url.strip())


def health_check(timeout: float = 3.0) -> bool:
    """Cheap liveness probe used by ``/health``; never raises."""
    if not is_ml_service_configured():
        return False
    try:
        response = httpx.get(f"{settings.ml_service_url.rstrip('/')}/health", timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def request_forecast(
    *,
    commodity_slug: str,
    market_slug: str,
    horizon_days: int,
    history: list[tuple[date, Decimal]],
    model: str = "auto",
) -> MLForecastResult | None:
    """Ask the ML service for a forecast; ``None`` means "use the fallback"."""
    if not is_ml_service_configured():
        logger.info("ML service disabled by configuration; using local baseline")
        return None

    payload = {
        "commodity_slug": commodity_slug,
        "market_slug": market_slug,
        "horizon_days": horizon_days,
        "model": model,
        "history": [
            {"date": observed_on.isoformat(), "price_pkr": float(price)}
            for observed_on, price in history
        ],
    }

    url = f"{settings.ml_service_url.rstrip('/')}/predict"
    try:
        with httpx.Client(timeout=settings.ml_service_timeout_seconds) as client:
            response = client.post(url, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("ML service request failed (%s); using local baseline", exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "ML service returned HTTP %s; using local baseline", response.status_code
        )
        return None

    try:
        body = response.json()
        points = [
            {
                "target_date": date.fromisoformat(point["target_date"]),
                "predicted_price_pkr": _to_decimal(point["predicted_price_pkr"]),
                "lower_bound_pkr": _to_decimal(point.get("lower_bound_pkr")),
                "upper_bound_pkr": _to_decimal(point.get("upper_bound_pkr")),
            }
            for point in body["points"]
        ]
        if len(points) != horizon_days:
            logger.warning(
                "ML service returned %s points for a %s-day horizon; using local baseline",
                len(points),
                horizon_days,
            )
            return None
        return MLForecastResult(
            model_name=body.get("model_name", "unknown"),
            issued_on=date.fromisoformat(body["issued_on"]),
            points=points,
            mae=_to_decimal(body.get("mae")),
            rmse=_to_decimal(body.get("rmse")),
            metrics=body.get("metrics") or {},
        )
    except (KeyError, TypeError, ValueError) as exc:
        # A malformed response is a bug in the ML service, not a reason to fail
        # the request: log it precisely and degrade.
        logger.warning("Malformed ML service response (%s); using local baseline", exc)
        return None
