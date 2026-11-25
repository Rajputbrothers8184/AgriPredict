"""Forecast endpoints: ML service first, documented local baseline as fallback.

The response always states which model produced the numbers, its measured error,
and whether it is a fallback. A farmer acting on a forecast deserves to know
whether it came from the trained model or a statistical stand-in.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Commodity, Forecast, ForecastPoint, Market
from app.schemas import (
    CommodityRead,
    ForecastPointRead,
    ForecastRead,
    MarketRead,
)
from app.services import market_service, ml_client
from app.services.baseline_forecast import MIN_OBSERVATIONS, forecast_seasonal_naive
from app.services.finance_service import as_decimal
from app.services.market_service import MarketDataNotFound

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])

DISCLAIMER = (
    "A forecast is an estimate from historical prices, not a guarantee. Use it "
    "alongside local market information before deciding when to sell."
)
MIN_HISTORY = 30


@router.get(
    "/{commodity_slug}/{market_slug}",
    response_model=ForecastRead,
    summary="Get a 7- or 30-day price forecast",
)
def get_forecast(
    commodity_slug: str,
    market_slug: str,
    session: DbSession,
    _user: CurrentUser,
    horizon: int = Query(default=7, description="7 or 30 days"),
    refresh: bool = Query(default=False, description="Ignore the cached forecast"),
):
    if horizon not in (7, 30):
        raise ValidationError(
            "horizon must be 7 or 30 days.", details={"field": "horizon"}
        )

    try:
        commodity = market_service.get_commodity_by_slug(session, commodity_slug)
        market = market_service.get_market_by_slug(session, market_slug)
    except MarketDataNotFound as exc:
        raise NotFoundError(str(exc)) from exc

    if not refresh:
        cached = _cached_forecast(session, commodity, market, horizon)
        if cached is not None:
            return cached

    series = market_service.price_series(session, commodity.id, market.id, limit=365)
    if len(series) < MIN_OBSERVATIONS:
        raise ValidationError(
            f"Not enough price history for {commodity.name_en} at {market.name}: "
            f"{len(series)} of {MIN_OBSERVATIONS} observations required. "
            "Forecasting needs a longer price series.",
            details={"observations": len(series), "required": MIN_OBSERVATIONS},
        )

    # 1) Try the trained ML service.
    ml_result = ml_client.request_forecast(
        commodity_slug=commodity.slug,
        market_slug=market.slug,
        horizon_days=horizon,
        history=series,
    )

    if ml_result is not None:
        record = _persist(
            session,
            commodity,
            market,
            model_name=ml_result.model_name if ml_result.model_name in
            {"seasonal_naive", "xgboost", "chronos"} else "seasonal_naive",
            horizon=horizon,
            issued_on=ml_result.issued_on,
            points=ml_result.points,
            mae=ml_result.mae,
            rmse=ml_result.rmse,
            metrics=ml_result.metrics,
        )
        return _to_schema(record, series, is_fallback=False)

    # 2) Degrade to the local baseline, clearly labelled.
    logger.info(
        "using local baseline forecast for %s/%s (ML service unavailable)",
        commodity.slug,
        market.slug,
    )
    try:
        baseline = forecast_seasonal_naive(series, horizon_days=horizon)
    except ValueError as exc:
        raise ValidationError(
            f"Not enough dependable history to forecast: {exc}",
            details={"observations": len(series)},
        ) from exc

    points = [
        {
            "target_date": point.target_date,
            "predicted_price_pkr": point.predicted,
            "lower_bound_pkr": point.lower,
            "upper_bound_pkr": point.upper,
        }
        for point in baseline.points
    ]
    record = _persist(
        session,
        commodity,
        market,
        model_name="seasonal_naive",
        horizon=horizon,
        issued_on=series[-1][0],
        points=points,
        mae=baseline.mae,
        rmse=baseline.rmse,
        metrics=baseline.metrics,
    )
    return _to_schema(record, series, is_fallback=True, note=baseline.note)


@router.get(
    "/latest/{commodity_slug}/{market_slug}",
    response_model=ForecastRead,
    summary="Most recent stored forecast (no regeneration)",
)
def latest_forecast(
    commodity_slug: str,
    market_slug: str,
    session: DbSession,
    _user: CurrentUser,
    horizon: int = Query(default=7),
):
    try:
        commodity = market_service.get_commodity_by_slug(session, commodity_slug)
        market = market_service.get_market_by_slug(session, market_slug)
    except MarketDataNotFound as exc:
        raise NotFoundError(str(exc)) from exc
    record = _latest_record(session, commodity.id, market.id, horizon)
    if record is None:
        raise NotFoundError("No forecast has been generated yet for this pair.")
    series = market_service.price_series(session, commodity.id, market.id, limit=365)
    return _to_schema(record, series, is_fallback=None)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _latest_record(
    session, commodity_id: int, market_id: int, horizon: int
) -> Forecast | None:
    return session.scalar(
        select(Forecast)
        .options(selectinload(Forecast.points))
        .where(
            Forecast.commodity_id == commodity_id,
            Forecast.market_id == market_id,
            Forecast.horizon_days == horizon,
        )
        .order_by(Forecast.created_at.desc(), Forecast.id.desc())
        .limit(1)
    )


def _cached_forecast(session, commodity: Commodity, market: Market, horizon: int) -> ForecastRead | None:
    from app.core.config import settings

    record = _latest_record(session, commodity.id, market.id, horizon)
    if record is None:
        return None
    created = record.created_at
    if created.tzinfo is None:
        from datetime import timezone

        created = created.replace(tzinfo=timezone.utc)
    from datetime import datetime, timezone

    age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
    if age_minutes > settings.forecast_cache_minutes:
        return None
    series = market_service.price_series(session, commodity.id, market.id, limit=365)
    return _to_schema(record, series, is_fallback=None)


def _persist(
    session,
    commodity: Commodity,
    market: Market,
    *,
    model_name: str,
    horizon: int,
    issued_on: date,
    points: list[dict],
    mae: Decimal | None,
    rmse: Decimal | None,
    metrics: dict,
) -> Forecast:
    record = Forecast(
        commodity_id=commodity.id,
        market_id=market.id,
        model_name=model_name,
        horizon_days=horizon,
        issued_on=issued_on,
        mae=mae,
        rmse=rmse,
        metrics_json=json.dumps(metrics) if metrics else None,
    )
    session.add(record)
    session.flush()
    for point in points:
        session.add(
            ForecastPoint(
                forecast_id=record.id,
                target_date=point["target_date"],
                predicted_price_pkr=point["predicted_price_pkr"],
                lower_bound_pkr=point.get("lower_bound_pkr"),
                upper_bound_pkr=point.get("upper_bound_pkr"),
            )
        )
    session.commit()
    session.refresh(record)
    return record


def _to_schema(
    record: Forecast,
    series: list[tuple[date, Decimal]],
    *,
    is_fallback: bool | None,
    note: str | None = None,
) -> ForecastRead:
    """Build the response, deriving the fallback flag from stored metrics."""
    metrics = None
    if record.metrics_json:
        try:
            metrics = json.loads(record.metrics_json)
        except json.JSONDecodeError:  # pragma: no cover - defensive
            metrics = None

    if is_fallback is None:
        is_fallback = bool(metrics and metrics.get("method") == "seasonal_naive_drift")

    last_observed = as_decimal(series[-1][1]) if series else None
    change_note = ""
    if last_observed and record.points:
        first = as_decimal(record.points[0].predicted_price_pkr)
        delta = ((first - last_observed) / last_observed * 100) if last_observed else None
        if delta is not None:
            direction = "rise" if delta > 0 else "fall" if delta < 0 else "hold"
            change_note = f" Expected to {direction} by {abs(delta):.1f}% on day 1."

    return ForecastRead(
        id=record.id,
        commodity=CommodityRead.model_validate(record.commodity),
        market=MarketRead.model_validate(record.market),
        model_name=record.model_name,  # type: ignore[arg-type]
        horizon_days=record.horizon_days,
        issued_on=record.issued_on,
        mae=record.mae,
        rmse=record.rmse,
        metrics=metrics,
        points=[
            ForecastPointRead(
                target_date=point.target_date,
                predicted_price_pkr=as_decimal(point.predicted_price_pkr),
                lower_bound_pkr=point.lower_bound_pkr,
                upper_bound_pkr=point.upper_bound_pkr,
            )
            for point in record.points
        ],
        is_fallback=is_fallback,
        disclaimer=(note or DISCLAIMER) + change_note,
    )
