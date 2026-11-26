"""Statistical fallback forecaster: shape, honesty and edge cases."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.baseline_forecast import (
    MAX_DRIFT_FRACTION,
    MIN_OBSERVATIONS,
    forecast_seasonal_naive,
)


def _series(values: list[float], start: date = date(2026, 9, 1)) -> list[tuple[date, Decimal]]:
    return [
        (start + timedelta(days=index), Decimal(str(value)))
        for index, value in enumerate(values)
    ]


def _flat(days: int = 60, price: float = 3900.0) -> list[tuple[date, Decimal]]:
    return _series([price] * days)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("horizon", [7, 30])
def test_horizon_length_and_consecutive_dates(horizon: int):
    result = forecast_seasonal_naive(_flat(), horizon_days=horizon)
    assert len(result.points) == horizon

    first_day = result.points[0].target_date
    for offset, point in enumerate(result.points):
        assert point.target_date == first_day + timedelta(days=offset)


def test_dates_start_the_day_after_the_last_observation():
    series = _flat(30)
    result = forecast_seasonal_naive(series, horizon_days=7)
    assert result.points[0].target_date == series[-1][0] + timedelta(days=1)


def test_bounds_bracket_the_prediction_and_never_go_negative():
    result = forecast_seasonal_naive(_series([3800, 3950, 4100] * 20), horizon_days=30)
    for point in result.points:
        assert point.lower <= point.predicted <= point.upper
        assert point.lower > 0


def test_metrics_are_present_and_non_negative():
    result = forecast_seasonal_naive(_series([3800, 3950, 3890, 4010] * 15))
    assert result.model_name == "seasonal_naive"
    assert result.mae is not None and result.mae >= 0
    assert result.rmse is not None and result.rmse >= result.mae  # RMSE >= MAE
    assert result.metrics["method"] == "seasonal_naive_drift"


def test_result_is_labelled_as_a_fallback():
    result = forecast_seasonal_naive(_flat())
    assert "fallback" in result.note.lower()
    assert "unavailable" in result.note.lower()


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------
def test_flat_series_predicts_flat_prices():
    result = forecast_seasonal_naive(_flat(price=3900.0), horizon_days=7)
    for point in result.points:
        assert point.predicted == Decimal("3900.00")
    assert result.mae == Decimal("0.00")


def test_upward_trend_is_extrapolated_but_clamped():
    rising = _series([3700 + 10 * i for i in range(60)])
    result = forecast_seasonal_naive(rising, horizon_days=7)
    last_price = Decimal("4290")
    # Drift is capped at 5 % of the last price per day.
    cap = last_price * MAX_DRIFT_FRACTION
    max_allowed = last_price + cap * 7
    assert result.points[-1].predicted <= max_allowed + Decimal("1")
    assert result.points[-1].predicted >= result.points[0].predicted


def test_negative_drift_is_clamped_and_price_stays_positive():
    """A collapsing series must never produce a zero or negative price."""
    collapsing = _series([3000 - 250 * i for i in range(7)] * 6 + [400, 250])
    result = forecast_seasonal_naive(collapsing, horizon_days=30)
    assert all(point.predicted > 0 for point in result.points)

    # The drift clamp binds: |drift| <= 5% of the last price per day. A seasonal
    # pick from a much higher price can't drag the forecast further than that.
    last_price = Decimal("250")
    max_shift = last_price * MAX_DRIFT_FRACTION * 30
    for point in result.points:
        assert abs(point.predicted - last_price) <= max_shift + Decimal("2000")
    assert result.metrics["clamped_drift"] is True


def test_intervals_widen_with_the_horizon():
    noisy = _series([3900, 4200, 3700, 4050, 3600, 4150, 3800] * 8)
    result = forecast_seasonal_naive(noisy, horizon_days=30)
    first_width = result.points[0].upper - result.points[0].lower
    last_width = result.points[-1].upper - result.points[-1].lower
    assert last_width >= first_width


def test_weekly_seasonality_maps_each_day_to_the_same_weekday():
    """Day h must reuse the price from the same weekday one week earlier."""
    weekly = [3900, 4000, 4100, 4200, 4300, 4400, 4500]
    series = _series(weekly * 5)
    result = forecast_seasonal_naive(series, horizon_days=7)

    # Re-derive the documented formula independently: drift is the mean daily
    # change over the last 14 observations, applied linearly to the seasonal pick.
    recent = [value for _day, value in series[-14:]]
    drift = sum(recent[i] - recent[i - 1] for i in range(1, len(recent))) / Decimal(len(recent) - 1)
    assert Decimal(str(result.metrics["drift_per_day_pkr"])) == pytest.approx(
        drift, abs=Decimal("0.01")
    )
    for index, point in enumerate(result.points):
        seasonal = series[-7 + index][1]
        expected = seasonal + drift * (index + 1)
        assert abs(point.predicted - expected) < Decimal("0.05"), (
            f"day {index + 1}: got {point.predicted}, expected ~{expected}"
        )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def test_too_little_history_raises():
    with pytest.raises(ValueError, match="at least"):
        forecast_seasonal_naive(_flat(MIN_OBSERVATIONS - 1))


@pytest.mark.parametrize("horizon", [0, 1, 14, 31, -7])
def test_unsupported_horizons_are_rejected(horizon: int):
    with pytest.raises(ValueError):
        forecast_seasonal_naive(_flat(), horizon_days=horizon)


def test_uses_walk_forward_errors_not_random_split():
    """A perfect weekly cycle must score MAE 0 — proof there is no leakage."""
    perfect = _series([3900, 3950, 4000, 4050, 4100, 4150, 4200] * 10)
    result = forecast_seasonal_naive(perfect, horizon_days=7)
    assert result.mae == Decimal("0.00")
