"""Model behaviour: shapes, determinism, invariants and serialisation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.seasonal_naive import SeasonalNaiveDriftForecaster, SeasonalNaiveForecaster
from models.xgboost_model import XGBoostForecaster

# ---------------------------------------------------------------------------
# Seasonal Naive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("horizon", [7, 30])
def test_seasonal_naive_produces_the_requested_length(seasonal_series, horizon):
    output = SeasonalNaiveForecaster().fit(seasonal_series).forecast(horizon=horizon)
    assert len(output.predictions) == horizon
    assert len(output.dates) == horizon
    assert output.dates[0] > seasonal_series.index[-1].date()


def test_seasonal_naive_repeats_the_weekly_pattern(flat_series):
    """On a flat series every prediction equals the level exactly."""
    output = SeasonalNaiveForecaster().fit(flat_series).forecast(horizon=14)
    assert all(value == pytest.approx(3900.0) for value in output.predictions)


def test_seasonal_naive_is_deterministic(seasonal_series):
    first = SeasonalNaiveForecaster().fit(seasonal_series).forecast(horizon=30)
    second = SeasonalNaiveForecaster().fit(seasonal_series).forecast(horizon=30)
    assert first.predictions == second.predictions


def test_seasonal_naive_rejects_a_series_shorter_than_the_season():
    index = pd.date_range("2026-01-01", periods=5, freq="D")
    with pytest.raises(ValueError, match="need more than"):
        SeasonalNaiveForecaster().fit(pd.Series(range(5), index=index, dtype=float))


def test_drift_variant_clamps_an_extreme_trend():
    """A drift above 5 % of the last price per day must be clamped to 5 %."""
    index = pd.date_range("2025-01-01", periods=10, freq="D")
    # 1000, 2000, … 10000: the last price is 10 000 and the daily change (1000)
    # is 10 % of it, so the 5 % cap must bind and halve the drift to 500.
    prices = pd.Series(1000.0 * np.arange(1, 11, dtype=float), index=index)
    forecaster = SeasonalNaiveDriftForecaster(season_length=7).fit(prices)
    output = forecaster.forecast(horizon=7)

    assert output.metadata["clamped_drift"] is True
    assert output.metadata["drift_per_day_pkr"] == pytest.approx(500.0)
    # Day 1 = same weekday last week (4000) + one clamped step (500).
    assert output.predictions[0] == pytest.approx(4500.0)


def test_drift_variant_never_predicts_a_negative_price():
    index = pd.date_range("2025-01-01", periods=90, freq="D")
    prices = pd.Series(np.linspace(5000, 200, 90), index=index)
    output = SeasonalNaiveDriftForecaster().fit(prices).forecast(horizon=30)
    assert all(value > 0 for value in output.predictions)


def test_bounds_always_bracket_the_prediction(seasonal_series):
    output = SeasonalNaiveDriftForecaster().fit(seasonal_series).forecast(horizon=30)
    for lower, predicted, upper in zip(output.lower, output.predictions, output.upper):
        assert lower <= predicted <= upper


# ---------------------------------------------------------------------------
# XGBoost
# ---------------------------------------------------------------------------


def test_xgboost_reports_availability():
    forecaster = XGBoostForecaster()
    if not forecaster.is_available:
        pytest.skip("xgboost is not installed in this environment")
    assert forecaster.unavailable_reason is None


def test_xgboost_trains_and_forecasts(seasonal_series):
    forecaster = XGBoostForecaster(horizon=7)
    if not forecaster.is_available:
        pytest.skip("xgboost is not installed")
    fitted = forecaster.fit(seasonal_series, 7)
    output = fitted.forecast(horizon=30)
    assert len(output.predictions) == 30
    assert all(value > 0 for value in output.predictions)
    assert output.model_name == "xgboost"


def test_xgboost_prediction_stays_within_a_sane_band(seasonal_series):
    forecaster = XGBoostForecaster(horizon=7)
    if not forecaster.is_available:
        pytest.skip("xgboost is not installed")
    output = forecaster.fit(seasonal_series, 7).forecast(horizon=30)
    observed_min = seasonal_series.min() * 0.6
    observed_max = seasonal_series.max() * 1.4
    assert all(observed_min <= value <= observed_max for value in output.predictions)


def test_xgboost_feature_importance_covers_lag_features(seasonal_series):
    forecaster = XGBoostForecaster(horizon=7)
    if not forecaster.is_available:
        pytest.skip("xgboost is not installed")
    forecaster.fit(seasonal_series, 7)
    importance = forecaster.feature_importance(top_n=5)
    assert len(importance) == 5
    assert sum(importance.values()) > 0


def test_xgboost_is_deterministic(seasonal_series):
    if not XGBoostForecaster().is_available:
        pytest.skip("xgboost is not installed")
    first = XGBoostForecaster(horizon=7).fit(seasonal_series, 7).forecast(horizon=7)
    second = XGBoostForecaster(horizon=7).fit(seasonal_series, 7).forecast(horizon=7)
    assert first.predictions == second.predictions


def test_xgboost_save_and_load_round_trip(seasonal_series, tmp_path):
    if not XGBoostForecaster().is_available:
        pytest.skip("xgboost is not installed")
    path = tmp_path / "model.joblib"
    original = XGBoostForecaster(horizon=7).fit(seasonal_series, 7)
    original.save(path)

    restored = XGBoostForecaster.load(path)
    assert restored.horizon == 7
    # Prediction intervals must survive the round trip (a bug found in live
    # testing: target_sd was not persisted, so lower == upper == prediction).
    restored._last_series = seasonal_series
    restored._last_date = seasonal_series.index[-1].date()
    output = restored.forecast(horizon=7)
    assert output.lower != output.upper
    assert all(lo < hi for lo, hi in zip(output.lower, output.upper))


def test_xgboost_rejects_a_too_short_series():
    if not XGBoostForecaster().is_available:
        pytest.skip("xgboost is not installed")
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    prices = pd.Series(np.arange(10, dtype=float) + 3000, index=index)
    with pytest.raises(ValueError):
        XGBoostForecaster(horizon=30).fit(prices, 30)


# ---------------------------------------------------------------------------
# ForecastOutput contract
# ---------------------------------------------------------------------------


def test_output_records_are_json_ready(seasonal_series):
    output = SeasonalNaiveForecaster().fit(seasonal_series).forecast(horizon=7)
    records = output.as_records()
    assert len(records) == 7
    for record in records:
        assert isinstance(record["target_date"], str)
        assert isinstance(record["predicted_price_pkr"], float)
        assert record["predicted_price_pkr"] > 0


def test_output_rejects_mismatched_lengths():
    from models import ForecastOutput

    with pytest.raises(ValueError, match="same length"):
        ForecastOutput(model_name="x", dates=[], predictions=[1.0])
