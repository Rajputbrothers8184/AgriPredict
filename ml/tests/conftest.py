"""Shared fixtures. Every test runs without network access or model weights."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ML_ROOT = Path(__file__).resolve().parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))


@pytest.fixture()
def daily_index() -> pd.DatetimeIndex:
    return pd.date_range("2025-01-01", periods=400, freq="D")


@pytest.fixture()
def seasonal_series(daily_index: pd.DatetimeIndex) -> pd.Series:
    """Price series with annual + weekly seasonality and noise (deterministic)."""
    rng = np.random.default_rng(7)
    t = np.arange(len(daily_index), dtype=float)
    values = (
        3900.0
        + 300.0 * np.sin(2 * np.pi * t / 365.25)
        + 150.0 * np.sin(2 * np.pi * t / 7.0)
        + rng.normal(0, 25, len(daily_index))
    )
    return pd.Series(values, index=daily_index, name="price_pkr")


@pytest.fixture()
def flat_series(daily_index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(np.full(len(daily_index), 3900.0), index=daily_index)


@pytest.fixture()
def raw_frame() -> pd.DataFrame:
    """A small valid long-format frame in the pipeline's schema."""
    dates = pd.date_range("2026-01-01", periods=40, freq="D").strftime("%Y-%m-%d")
    rows = []
    for commodity in ("wheat", "potato"):
        for market in ("lahore-sabzi-mandi", "multan-mandi"):
            for offset, day in enumerate(dates):
                base = 3900.0 if commodity == "wheat" else 2200.0
                rows.append(
                    {
                        "date": day,
                        "commodity": commodity,
                        "market": market,
                        "price_pkr": base + offset,
                        "source": "synthetic_fixture",
                    }
                )
    return pd.DataFrame(rows)
