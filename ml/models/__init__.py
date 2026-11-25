"""Forecasting models behind one small interface.

Every model implements ``BaseForecaster``::

    forecast(series: pd.Series, horizon: int) -> ForecastOutput

`ForecastOutput` carries the predicted path, optional intervals, the model name
and any metadata (including a degradation reason). Because the interface is
uniform, the evaluation harness and the inference service treat the learned and
baseline models identically, which is what makes an honest comparison possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class ForecastOutput:
    model_name: str
    dates: list[date]
    predictions: list[float]
    lower: list[float] | None = None
    upper: list[float] | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.predictions):
            raise ValueError("dates and predictions must be the same length")
        if self.lower is not None and len(self.lower) != len(self.predictions):
            raise ValueError("lower bound must match the prediction length")
        if self.upper is not None and len(self.upper) != len(self.predictions):
            raise ValueError("upper bound must match the prediction length")

    def as_records(self) -> list[dict]:
        records = []
        for index, (day, value) in enumerate(zip(self.dates, self.predictions)):
            records.append(
                {
                    "target_date": day.isoformat(),
                    "predicted_price_pkr": round(float(value), 2),
                    "lower_bound_pkr": round(float(self.lower[index]), 2)
                    if self.lower
                    else None,
                    "upper_bound_pkr": round(float(self.upper[index]), 2)
                    if self.upper
                    else None,
                }
            )
        return records


class BaseForecaster:
    """Protocol every forecaster follows."""

    name: str = "base"

    def forecast(self, series: pd.Series, horizon: int) -> ForecastOutput:
        raise NotImplementedError

    def fit(self, series: pd.Series, horizon: int) -> "BaseForecaster":
        """Fit on a training series. Baselines need no fitting and return self."""
        raise NotImplementedError

    @property
    def is_available(self) -> bool:
        """False when an optional dependency or model artefact is missing."""
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None


__all__ = ["BaseForecaster", "ForecastOutput"]
