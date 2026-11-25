"""Feature engineering for the XGBoost forecaster.

Design constraints that matter for correctness
---------------------------------------------
1. **Only information available at forecast time is used.** Every feature for
   day *t* is computed from prices up to and including *t*. The target is
   ``price[t + h]``.
2. **No shuffling.** The train/test split is strictly chronological.
3. **Lags are on the calendar, not on the row index.** Because the loader
   reindexes to a complete daily series, ``shift(7)`` really is "a week ago".
4. **Direct multi-horizon targets.** A model is trained per horizon instead of
   being iterated recursively, which stops one-step errors from compounding over
   a 30-day forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import LAG_DAYS, ROLLING_WINDOWS

CALENDAR_FEATURES = (
    "day_of_year",
    "month",
    "day_of_week",
    "is_month_start",
    "is_month_end",
)


def build_supervised(
    prices: pd.Series,
    horizon: int,
    *,
    lags: tuple[int, ...] = LAG_DAYS,
    windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> pd.DataFrame:
    """Build a supervised frame for one series and one forecast horizon.

    Parameters
    ----------
    prices
        Daily price series indexed by date, oldest first, no gaps.
    horizon
        Number of days ahead to predict.

    Returns
    -------
    DataFrame with feature columns, a ``target`` column (price at t+horizon) and
    a ``date`` index carrying the *feature* date. Rows where any feature or the
    target is undefined are dropped.
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if len(prices) < max(lags) + max(windows) + horizon + 5:
        raise ValueError(
            f"series too short for horizon {horizon}: {len(prices)} observations"
        )

    frame = _engineer(prices)
    # ``lags``/``windows`` parameters exist for experimentation; the shared
    # ``_engineer`` uses the module defaults so training and inference match.
    _ = (lags, windows)

    # --- Target: the price `horizon` days later ---------------------------
    frame["target"] = frame["price"].shift(-horizon)
    frame["target_date"] = frame.index.to_series().shift(-horizon)

    return frame.dropna()


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Model input columns, excluding the target and bookkeeping fields."""
    excluded = {"price", "target", "target_date"}
    return [column for column in frame.columns if column not in excluded]


def _engineer(prices: pd.Series) -> pd.DataFrame:
    """Feature block shared by training and inference (single implementation)."""
    frame = pd.DataFrame({"price": prices.astype(float)}, index=prices.index)
    for lag in LAG_DAYS:
        frame[f"lag_{lag}"] = frame["price"].shift(lag)
    for window in ROLLING_WINDOWS:
        shifted = frame["price"].shift(1)
        frame[f"roll_mean_{window}"] = shifted.rolling(window).mean()
        frame[f"roll_std_{window}"] = shifted.rolling(window).std()
        frame[f"roll_min_{window}"] = shifted.rolling(window).min()
        frame[f"roll_max_{window}"] = shifted.rolling(window).max()
    frame["diff_1"] = frame["price"].diff(1)
    frame["diff_7"] = frame["price"].diff(7)
    frame["diff_30"] = frame["price"].diff(30)
    frame["pct_change_7"] = frame["price"].pct_change(7).replace([np.inf, -np.inf], np.nan)
    frame["pct_change_30"] = frame["price"].pct_change(30).replace([np.inf, -np.inf], np.nan)

    index = pd.DatetimeIndex(frame.index)
    frame["day_of_year"] = index.dayofyear
    frame["month"] = index.month
    frame["day_of_week"] = index.dayofweek
    frame["is_month_start"] = index.is_month_start.astype(int)
    frame["is_month_end"] = index.is_month_end.astype(int)
    frame["sin_doy"] = np.sin(2 * np.pi * frame["day_of_year"] / 365.25)
    frame["cos_doy"] = np.cos(2 * np.pi * frame["day_of_year"] / 365.25)
    return frame


def last_feature_row(prices: pd.Series) -> pd.DataFrame:
    """Features for the newest observation — the row used to forecast ahead.

    ``build_supervised`` drops rows whose target is unknown, so inferring the
    future needs the final feature row explicitly. It is computed by the same
    ``_engineer`` helper as training, which is what guarantees the training and
    inference feature spaces cannot diverge.
    """
    work = _engineer(prices)
    row = work.iloc[[-1]].copy()
    row["target"] = np.nan
    row["target_date"] = pd.NaT
    if row[feature_columns(work)].isna().any(axis=1).iloc[0]:
        raise ValueError(
            "insufficient history to compute the newest feature row "
            f"({len(prices)} observations, need at least {max(ROLLING_WINDOWS) + 1})"
        )
    return row
