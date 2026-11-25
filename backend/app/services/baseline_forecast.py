"""Statistical fallback forecaster for when the ML service is unreachable.

Why this exists
---------------
The Android app must remain useful when the ML service is down, when the phone
is offline and the backend only has cached data, or when a commodity has too
little history for XGBoost/Chronos. Rather than returning an error or, worse,
inventing numbers, the API returns a *documented* baseline forecast and labels it
as a fallback with its measured error.

Method (Seasonal Naive with drift)
----------------------------------
1. Take the last ``season_length`` observations (default 7 days, hence weekly
   seasonality).
2. For each future step ``h``, predict ``last_week_same_weekday + h × drift``,
   where ``drift`` is the mean daily change over the recent window, clamped to
   a configurable fraction of the last price so a noisy week cannot produce an
   absurd projection.
3. Confidence bounds widen with ``sqrt(h)`` from the residual standard
   deviation — a straight, honest statement of growing uncertainty.

This is deliberately simple: it is the benchmark the ML models must beat, and
its presence in the repository makes that comparison reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.services.finance_service import as_decimal, money_or_zero, round_money

MIN_OBSERVATIONS = 8
DEFAULT_SEASON_LENGTH = 7
MAX_DRIFT_FRACTION = Decimal("0.05")  # ≤5% of the last price per day


@dataclass(frozen=True)
class BaselinePoint:
    target_date: date
    predicted: Decimal
    lower: Decimal
    upper: Decimal


@dataclass(frozen=True)
class BaselineResult:
    model_name: str
    points: list[BaselinePoint]
    mae: Decimal | None
    rmse: Decimal | None
    note: str
    metrics: dict = field(default_factory=dict)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _in_sample_errors(series: list[Decimal], season_length: int) -> tuple[Decimal, Decimal, Decimal]:
    """Walk-forward (expanding-origin) errors — never a random split.

    For each index ``i`` from ``season_length`` onwards, predict the value from
    one season earlier and compare. This mirrors how the model will actually be
    used and cannot leak future information into the fit.
    """
    errors: list[Decimal] = []
    for i in range(season_length, len(series)):
        predicted = series[i - season_length]
        errors.append(series[i] - predicted)

    if not errors:
        return Decimal("0"), Decimal("0"), Decimal("0")

    abs_errors = [abs(e) for e in errors]
    mae = money_or_zero(_mean(abs_errors))
    rmse = money_or_zero(
        Decimal(math.sqrt(float(_mean([e * e for e in errors]))))
    )
    residual_sd = Decimal(
        math.sqrt(float(_mean([(e - _mean(errors)) ** 2 for e in errors])))
    )
    return mae, rmse, residual_sd


def forecast_seasonal_naive(
    series: list[tuple[date, Decimal]],
    horizon_days: int = 7,
    *,
    season_length: int = DEFAULT_SEASON_LENGTH,
) -> BaselineResult:
    """Produce a seasonal-naive forecast with drift and widening intervals.

    ``series`` must be ``(date, avg_price)`` pairs sorted oldest → newest and
    contain no duplicate dates (the API guarantees this via the unique price
    constraint).
    """
    if horizon_days not in (7, 30):
        raise ValueError("horizon_days must be 7 or 30")
    if len(series) < MIN_OBSERVATIONS:
        raise ValueError(
            f"at least {MIN_OBSERVATIONS} price observations are required, "
            f"got {len(series)}"
        )

    dates = [d for d, _ in series]
    values = [as_decimal(v) for _, v in series]
    last_date, last_price = dates[-1], values[-1]

    # Mean daily drift over the recent window, clamped to a sane band.
    recent = values[-max(season_length * 2, 14) :]
    per_step_changes = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
    raw_drift = _mean(per_step_changes) if per_step_changes else Decimal("0")
    limit = last_price * MAX_DRIFT_FRACTION
    drift = max(min(raw_drift, limit), -limit)

    mae, rmse, residual_sd = _in_sample_errors(values, season_length)

    points: list[BaselinePoint] = []
    for step in range(1, horizon_days + 1):
        season_value = values[-season_length + ((step - 1) % season_length)]
        predicted = season_value + drift * step
        # Prices cannot be negative; clamp rather than emit an impossible value.
        predicted = max(predicted, Decimal("0.01"))
        widening = residual_sd * Decimal(math.sqrt(step))
        points.append(
            BaselinePoint(
                target_date=last_date + timedelta(days=step),
                predicted=money_or_zero(predicted),
                lower=money_or_zero(max(predicted - widening, Decimal("0.01"))),
                upper=money_or_zero(predicted + widening),
            )
        )

    return BaselineResult(
        model_name="seasonal_naive",
        points=points,
        mae=mae,
        rmse=rmse,
        note=(
            "Fallback forecast produced by the backend (seasonal naive with drift). "
            "The ML service was unavailable; accuracy is measured on historical "
            "data only and is indicative."
        ),
        metrics={
            "method": "seasonal_naive_drift",
            "season_length": season_length,
            "observations": len(values),
            "drift_per_day_pkr": float(money_or_zero(drift)),
            "residual_sd_pkr": float(money_or_zero(residual_sd)),
            "clamped_drift": raw_drift != drift,
        },
    )
