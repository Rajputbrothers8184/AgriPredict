"""Metric correctness and the rolling-origin backtest protocol.

The metric tests use hand-computed values: if MAE/RMSE are wrong, every reported
number in the project is wrong, and a self-consistent test would hide that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation.backtest import _fold_boundaries, backtest_model, compare_models
from evaluation.metrics import (
    bias,
    error_by_horizon_step,
    mae,
    mape,
    mase,
    rmse,
    summarize,
)
from models.seasonal_naive import SeasonalNaiveDriftForecaster, SeasonalNaiveForecaster


# ---------------------------------------------------------------------------
# Metrics — hand-computed
# ---------------------------------------------------------------------------
def test_mae_hand_computed():
    # |10-12| = 2, |20-17| = 3 -> mean 2.5
    assert mae(np.array([10.0, 20.0]), np.array([12.0, 17.0])) == pytest.approx(2.5)


def test_rmse_hand_computed():
    # sqrt((4 + 9)/2) = sqrt(6.5) = 2.5495...
    assert rmse(np.array([10.0, 20.0]), np.array([12.0, 17.0])) == pytest.approx(
        np.sqrt(6.5)
    )


def test_mape_hand_computed():
    # (|2|/10 + |3|/20)/2 * 100 = (0.2 + 0.15)/2*100 = 17.5
    assert mape(np.array([10.0, 20.0]), np.array([12.0, 17.0])) == pytest.approx(17.5)


def test_mape_returns_none_when_an_actual_is_zero():
    """Never silently drop zero-valued points to flatter the model."""
    assert mape(np.array([0.0, 20.0]), np.array([1.0, 17.0])) is None


def test_bias_sign_convention():
    # Predicted higher than actual -> positive bias (over-prediction).
    assert bias(np.array([10.0, 10.0]), np.array([12.0, 14.0])) == pytest.approx(3.0)


def test_mase_of_one_means_parity_with_seasonal_naive():
    training = np.array([10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0])
    # Scale = mean |diff over 7 lags| across the training set.
    scale = np.mean(np.abs(training[7:] - training[:-7]))
    actual = np.array([15.0, 16.0])
    predicted = actual + scale  # exactly one scale unit of error
    assert mase(actual, predicted, training, season_length=7) == pytest.approx(1.0)


def test_summarize_packages_every_metric():
    actual = np.array([100.0, 110.0, 120.0])
    predicted = np.array([102.0, 108.0, 121.0])
    result = summarize(actual, predicted, training=np.arange(50, dtype=float) + 100)
    payload = result.as_dict()
    assert payload["observations"] == 3
    assert payload["unit"] == "PKR/40kg"
    assert payload["rmse"] >= payload["mae"]  # mathematically guaranteed


def test_summarize_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        summarize(np.array([1.0, 2.0]), np.array([1.0]))


def test_error_by_horizon_step_is_per_day():
    rows = error_by_horizon_step(np.array([100.0, 200.0]), np.array([90.0, 220.0]))
    assert rows[0] == {
        "day": 1,
        "actual": 100.0,
        "predicted": 90.0,
        "abs_error": 10.0,
        "signed_error": -10.0,
    }
    assert rows[1]["abs_error"] == 20.0


# ---------------------------------------------------------------------------
# Backtest protocol
# ---------------------------------------------------------------------------
def test_fold_boundaries_never_use_future_data():
    boundaries = _fold_boundaries(n_obs=500, horizon=30, folds=3)
    assert boundaries, "expected folds for a 500-point series"
    for train_end, test_end in boundaries:
        assert train_end < test_end <= 500, "test window must follow the train window"
    # Folds march forward in time.
    assert boundaries == sorted(boundaries)


def test_fold_boundaries_respect_the_minimum_training_size():
    boundaries = _fold_boundaries(n_obs=300, horizon=30, folds=5)
    for train_end, _test_end in boundaries:
        assert train_end >= 180


def test_short_series_produces_no_folds_and_says_why():
    index = pd.date_range("2026-01-01", periods=40, freq="D")
    prices = pd.Series(np.arange(40, dtype=float) + 3000, index=index)
    result = backtest_model(SeasonalNaiveForecaster(), prices, horizon=30)
    assert result.folds == []
    assert result.notes and "too short" in result.notes[0]


def test_backtest_produces_out_of_sample_predictions(seasonal_series):
    result = backtest_model(SeasonalNaiveDriftForecaster(), seasonal_series, horizon=7, folds=3)
    assert len(result.folds) == 3
    for fold in result.folds:
        assert len(fold.predictions) == len(fold.actuals) > 0
        assert fold.metrics["observations"] == len(fold.predictions)
        # Test windows move strictly forward.
    assert result.folds[0].test_start < result.folds[-1].test_end


def test_backtest_training_windows_expand(seasonal_series):
    result = backtest_model(SeasonalNaiveForecaster(), seasonal_series, horizon=7, folds=4)
    sizes = [fold.train_size for fold in result.folds]
    assert sizes == sorted(sizes), "each fold must train on more history than the last"


def test_aggregate_metrics_average_the_folds(seasonal_series):
    result = backtest_model(SeasonalNaiveDriftForecaster(), seasonal_series, horizon=7, folds=3)
    aggregate = result.aggregate
    fold_maes = [fold.metrics["mae"] for fold in result.folds]
    assert aggregate["mae"] == pytest.approx(sum(fold_maes) / len(fold_maes), abs=0.01)
    assert aggregate["folds"] == 3


def test_compare_models_ranks_by_mae_and_reports_a_winner(seasonal_series):
    comparison = compare_models(
        {
            "seasonal_naive": SeasonalNaiveDriftForecaster(),
            "xgboost": __import__("models.xgboost_model", fromlist=["XGBoostForecaster"]).XGBoostForecaster(horizon=7),
        },
        seasonal_series,
        horizon=7,
        folds=3,
    )
    if len(comparison["ranking"]) < 2:
        pytest.skip("xgboost unavailable in this environment")
    maes = [
        comparison["models"][name]["aggregate"]["mae"] for name in comparison["ranking"]
    ]
    assert maes == sorted(maes), "ranking must be ordered by MAE"
    assert comparison["winner"] == comparison["ranking"][0]
    assert "synthetic fixture" in comparison["caveat"].lower()


def test_compare_models_records_an_unavailable_model_rather_than_crashing(seasonal_series):
    class Broken:
        name = "broken"

        @property
        def is_available(self) -> bool:
            return False

        @property
        def unavailable_reason(self) -> str:
            return "deliberately unavailable for this test"

        def fit(self, *_args, **_kwargs):
            raise AssertionError("must not be called")

        def forecast(self, *_args, **_kwargs):
            raise AssertionError("must not be called")

    comparison = compare_models({"broken": Broken()}, seasonal_series, horizon=7, folds=2)
    notes = comparison["models"]["broken"]["notes"]
    assert any("unavailable" in note for note in notes)
    assert comparison["winner"] is None
