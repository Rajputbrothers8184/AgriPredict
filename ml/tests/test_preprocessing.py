"""Dataset validation, cleaning and feature engineering."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from preprocessing.features import (
    build_supervised,
    feature_columns,
    last_feature_row,
)
from preprocessing.loaders import (
    DatasetValidationError,
    clean_frame,
    load_price_frame,
    series_for,
    validate_schema,
    validate_values,
)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
def test_valid_frame_passes(raw_frame: pd.DataFrame):
    validate_schema(raw_frame)
    validate_values(raw_frame)


@pytest.mark.parametrize("column", ["date", "commodity", "market", "price_pkr"])
def test_missing_required_column_is_rejected(raw_frame: pd.DataFrame, column: str):
    with pytest.raises(DatasetValidationError, match="missing required column"):
        validate_schema(raw_frame.drop(columns=[column]))


def test_empty_frame_is_rejected(raw_frame: pd.DataFrame):
    with pytest.raises(DatasetValidationError, match="no rows"):
        validate_schema(raw_frame.iloc[0:0])


def test_unparseable_dates_are_rejected(raw_frame: pd.DataFrame):
    frame = raw_frame.copy()
    frame.loc[0, "date"] = "not-a-date"
    with pytest.raises(DatasetValidationError, match="unparseable date"):
        validate_values(frame)


@pytest.mark.parametrize("bad", ["Wheat", "Red Chilli", "wheat_fine", ""])
def test_non_slug_commodity_is_rejected(raw_frame: pd.DataFrame, bad: str):
    frame = raw_frame.copy()
    frame.loc[0, "commodity"] = bad
    with pytest.raises(DatasetValidationError, match="not lowercase slugs"):
        validate_values(frame)


def test_per_kg_prices_are_caught_by_the_series_median_check(raw_frame: pd.DataFrame):
    """A whole series divided by 40 (per-kg instead of per-maund) must be loud.

    A single value of 97 is indistinguishable from a legitimate cheap commodity,
    so the check is applied to the series median — exactly where a unit error
    shows up.
    """
    frame = raw_frame.copy()
    frame["price_pkr"] = frame["price_pkr"] / 40.0
    frame.loc[:, "source"] = "manual"
    with pytest.raises(DatasetValidationError, match="per kilogram"):
        validate_values(frame)


def test_per_tonne_prices_are_caught_by_the_series_median_check(raw_frame: pd.DataFrame):
    frame = raw_frame.copy()
    frame["price_pkr"] = frame["price_pkr"] * 25.0  # per tonne instead of per maund
    with pytest.raises(DatasetValidationError, match="per tonne"):
        validate_values(frame)


def test_one_suspicious_point_among_valid_ones_is_not_a_unit_error(raw_frame: pd.DataFrame):
    """A single cheap quote must not invalidate an otherwise plausible series."""
    frame = raw_frame.copy()
    frame.loc[0, "price_pkr"] = 97.0
    validate_values(frame)  # no raise: the median is still ~3900


def test_absurd_price_is_rejected(raw_frame: pd.DataFrame):
    frame = raw_frame.copy()
    frame.loc[0, "price_pkr"] = 5_000_000
    with pytest.raises(DatasetValidationError, match="outside"):
        validate_values(frame)


def test_unknown_source_is_rejected(raw_frame: pd.DataFrame):
    frame = raw_frame.copy()
    frame.loc[0, "source"] = "made_up"
    with pytest.raises(DatasetValidationError, match="unknown source"):
        validate_values(frame)


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def test_clean_deduplicates_keeping_the_last_quote(raw_frame: pd.DataFrame):
    duplicated = pd.concat([raw_frame, raw_frame.iloc[[0]]], ignore_index=True)
    duplicated.loc[duplicated.index[-1], "price_pkr"] = 9999.0

    cleaned, profile = clean_frame(duplicated)
    assert profile["duplicates_removed"] == 1
    kept = cleaned[
        (cleaned.commodity == raw_frame.loc[0, "commodity"])
        & (cleaned.market == raw_frame.loc[0, "market"])
        & (cleaned.date == pd.Timestamp(raw_frame.loc[0, "date"]))
    ]
    assert len(kept) == 1


def test_clean_fills_short_gaps(raw_frame: pd.DataFrame):
    gappy = raw_frame.drop(index=[5, 6]).reset_index(drop=True)
    cleaned, profile = clean_frame(gappy)
    assert profile["gaps_filled"] >= 1
    assert cleaned["price_pkr"].isna().sum() == 0


def test_clean_flags_an_extra_zero_outlier(raw_frame: pd.DataFrame):
    frame = raw_frame.copy()
    # Simulate a data-entry slip: 3900 -> 390000 on one day.
    frame.loc[10, "price_pkr"] = 390_000.0
    frame.loc[10, "source"] = "manual"
    cleaned, profile = clean_frame(frame)
    assert profile["outliers_flagged"] >= 1
    corrected = cleaned[
        (cleaned.commodity == frame.loc[10, "commodity"])
        & (cleaned.market == frame.loc[10, "market"])
        & (cleaned.date == pd.Timestamp(frame.loc[10, "date"]))
    ]
    assert corrected["price_pkr"].iloc[0] < 100_000


def test_clean_produces_a_complete_daily_calendar(raw_frame: pd.DataFrame):
    cleaned, _profile = clean_frame(raw_frame)
    for (_commodity, _market), group in cleaned.groupby(["commodity", "market"]):
        deltas = group["date"].sort_values().diff().dropna().dt.days.unique()
        assert set(deltas) <= {1}, "series must be continuous after cleaning"


def test_clean_reports_its_own_provenance(raw_frame: pd.DataFrame):
    cleaned, profile = clean_frame(raw_frame)
    assert "synthetic_fixture" in profile["sources"]
    assert profile["output_rows"] == len(cleaned)


def test_load_price_frame_round_trip(tmp_path, raw_frame: pd.DataFrame):
    path = tmp_path / "prices.csv"
    raw_frame.to_csv(path, index=False)
    frame, profile = load_price_frame(path)
    assert len(frame) == len(raw_frame)
    assert profile["series"] == 4


def test_load_price_frame_validate_only_does_not_clean(tmp_path, raw_frame: pd.DataFrame):
    path = tmp_path / "prices.csv"
    raw_frame.to_csv(path, index=False)
    _frame, summary = load_price_frame(path, validate_only=True)
    assert summary["rows"] == len(raw_frame)
    assert summary["commodities"] == ["potato", "wheat"]


def test_series_for_unknown_pair_raises(raw_frame: pd.DataFrame):
    with pytest.raises(DatasetValidationError, match="no rows"):
        series_for(raw_frame, "wheat", "karachi-sabzi-mandi")


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def test_supervised_frame_has_lag_and_calendar_features():
    index = pd.date_range("2025-01-01", periods=200, freq="D")
    prices = pd.Series(np.linspace(3000, 4000, 200), index=index)
    frame = build_supervised(prices, horizon=7)
    columns = feature_columns(frame)
    for expected in ("lag_1", "lag_7", "roll_mean_7", "sin_doy", "cos_doy", "pct_change_30"):
        assert expected in columns
    assert "target" not in columns
    assert "price" not in columns


def test_target_is_the_price_horizon_days_ahead():
    index = pd.date_range("2025-01-01", periods=120, freq="D")
    prices = pd.Series(np.arange(120, dtype=float) + 3000, index=index)
    horizon = 7
    frame = build_supervised(prices, horizon=horizon)
    for _position, row in frame.head(5).iterrows():
        expected = prices.loc[pd.Timestamp(_position) + pd.Timedelta(days=horizon)]
        assert row["target"] == pytest.approx(expected)


def test_features_use_no_future_information():
    """lag_1 for day t must be day t−1, never t or later."""
    index = pd.date_range("2025-01-01", periods=120, freq="D")
    prices = pd.Series(np.arange(120, dtype=float) + 3000, index=index)
    frame = build_supervised(prices, horizon=1)
    # With a perfectly linear series, lag_1 is exactly one unit below the price.
    assert frame["lag_1"].iloc[0] == pytest.approx(prices.iloc[len(prices) - len(frame) - 2])


def test_short_series_raises_a_clear_error():
    index = pd.date_range("2025-01-01", periods=20, freq="D")
    prices = pd.Series(np.arange(20, dtype=float) + 3000, index=index)
    with pytest.raises(ValueError, match="too short"):
        build_supervised(prices, horizon=30)


def test_last_feature_row_matches_training_feature_space(seasonal_series):
    frame = build_supervised(seasonal_series, horizon=7)
    row = last_feature_row(seasonal_series)
    assert list(row[feature_columns(frame)].columns) == feature_columns(frame)
    assert not row[feature_columns(frame)].isna().any(axis=1).iloc[0]


def test_last_feature_row_needs_enough_history():
    index = pd.date_range("2025-01-01", periods=10, freq="D")
    prices = pd.Series(np.arange(10, dtype=float) + 3000, index=index)
    with pytest.raises(ValueError, match="insufficient history"):
        last_feature_row(prices)
