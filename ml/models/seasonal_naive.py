"""Seasonal Naive baseline — the benchmark every other model must beat.

Two variants are provided:

``SeasonalNaiveForecaster``
    The textbook definition: the forecast for day *h* is the price observed
    ``season_length`` days earlier. On weekly-seasonal price data this is a
    surprisingly strong baseline, and it is what the backend uses as its
    fallback when the ML service is unavailable.

``SeasonalNaiveDriftForecaster``
    Seasonal naive plus a drift term (mean daily change over the recent window,
    clamped). Slightly better on trending series, still explainable to a farmer:
    "the price usually moves this much per day, and it usually moves with the
    week".

Both report in-sample walk-forward errors, never a random-split score.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from models import BaseForecaster, ForecastOutput

DEFAULT_SEASON_LENGTH = 7
MAX_DRIFT_FRACTION = 0.05


class SeasonalNaiveForecaster(BaseForecaster):
    name = "seasonal_naive"

    def __init__(self, season_length: int = DEFAULT_SEASON_LENGTH) -> None:
        self.season_length = season_length
        self._history: np.ndarray | None = None
        self._last_date: date | None = None
        self._residual_sd: float = 0.0

    def fit(self, series: pd.Series, horizon: int = 30) -> "SeasonalNaiveForecaster":
        if len(series) <= self.season_length:
            raise ValueError(
                f"need more than {self.season_length} observations, got {len(series)}"
            )
        values = series.to_numpy(dtype=float)
        self._history = values
        self._last_date = series.index[-1].date()

        # Walk-forward residuals (never a random split).
        errors = values[self.season_length :] - values[: -self.season_length]
        self._residual_sd = float(np.std(errors)) if errors.size else 0.0
        return self

    def forecast(self, series: pd.Series | None = None, horizon: int = 30) -> ForecastOutput:
        if self._history is None:
            if series is None:
                raise ValueError("call fit() first, or pass a series")
            self.fit(series, horizon)

        assert self._history is not None and self._last_date is not None
        values = self._history
        predictions: list[float] = []
        lower: list[float] = []
        upper: list[float] = []

        for step in range(1, horizon + 1):
            seasonal_value = float(values[-self.season_length + ((step - 1) % self.season_length)])
            predicted = max(seasonal_value, 0.01)
            widening = self._residual_sd * float(np.sqrt(step))
            predictions.append(round(predicted, 2))
            lower.append(round(max(predicted - widening, 0.01), 2))
            upper.append(round(predicted + widening, 2))

        dates = [self._last_date + timedelta(days=step) for step in range(1, horizon + 1)]
        return ForecastOutput(
            model_name=self.name,
            dates=dates,
            predictions=predictions,
            lower=lower,
            upper=upper,
            metadata={
                "method": "seasonal_naive",
                "season_length": self.season_length,
                "observations": int(values.size),
                "residual_sd_pkr": round(self._residual_sd, 2),
            },
        )


class SeasonalNaiveDriftForecaster(BaseForecaster):
    """Seasonal naive with a clamped linear drift term."""

    name = "seasonal_naive"

    def __init__(
        self,
        season_length: int = DEFAULT_SEASON_LENGTH,
        drift_window: int | None = None,
    ) -> None:
        self.season_length = season_length
        self.drift_window = drift_window or max(season_length * 2, 14)
        self._history: np.ndarray | None = None
        self._last_date: date | None = None
        self._drift: float = 0.0
        self._residual_sd: float = 0.0
        self._clamped = False

    def fit(self, series: pd.Series, horizon: int = 30) -> "SeasonalNaiveDriftForecaster":
        if len(series) <= self.season_length:
            raise ValueError(
                f"need more than {self.season_length} observations, got {len(series)}"
            )
        values = series.to_numpy(dtype=float)
        self._history = values
        self._last_date = series.index[-1].date()

        recent = values[-self.drift_window :]
        per_step = np.diff(recent)
        raw_drift = float(per_step.mean()) if per_step.size else 0.0
        limit = float(values[-1]) * MAX_DRIFT_FRACTION
        self._drift = float(np.clip(raw_drift, -limit, limit))
        self._clamped = not np.isclose(raw_drift, self._drift)

        errors = values[self.season_length :] - values[: -self.season_length]
        self._residual_sd = float(np.std(errors)) if errors.size else 0.0
        return self

    def forecast(self, series: pd.Series | None = None, horizon: int = 30) -> ForecastOutput:
        if self._history is None:
            if series is None:
                raise ValueError("call fit() first, or pass a series")
            self.fit(series, horizon)

        assert self._history is not None and self._last_date is not None
        values = self._history
        predictions: list[float] = []
        lower: list[float] = []
        upper: list[float] = []

        for step in range(1, horizon + 1):
            seasonal_value = float(values[-self.season_length + ((step - 1) % self.season_length)])
            predicted = max(seasonal_value + self._drift * step, 0.01)
            widening = self._residual_sd * float(np.sqrt(step))
            predictions.append(round(predicted, 2))
            lower.append(round(max(predicted - widening, 0.01), 2))
            upper.append(round(predicted + widening, 2))

        dates = [self._last_date + timedelta(days=step) for step in range(1, horizon + 1)]
        return ForecastOutput(
            model_name=self.name,
            dates=dates,
            predictions=predictions,
            lower=lower,
            upper=upper,
            metadata={
                "method": "seasonal_naive_drift",
                "season_length": self.season_length,
                "observations": int(values.size),
                "drift_per_day_pkr": round(self._drift, 2),
                "residual_sd_pkr": round(self._residual_sd, 2),
                "clamped_drift": bool(self._clamped),
            },
        )
