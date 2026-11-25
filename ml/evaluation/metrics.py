"""Forecast error metrics, computed per horizon and in aggregate.

Definitions follow Hyndman & Athanasopoulos, *Forecasting: Principles and
Practice* (3rd ed.). Every metric here is scale-dependent and expressed in
**PKR per 40 kg**, because that is the unit a farmer and a supervisor can
interpret. A percentage error is additionally reported so two commodities at
different price levels can be compared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PRICE_UNIT = "PKR/40kg"


@dataclass(frozen=True)
class ErrorMetrics:
    """Error summary for one model on one series/horizon."""

    mae: float
    rmse: float
    mape: float | None
    bias: float
    mase: float | None
    observations: int

    def as_dict(self) -> dict:
        return {
            "mae": round(self.mae, 2),
            "rmse": round(self.rmse, 2),
            "mape_pct": round(self.mape, 2) if self.mape is not None else None,
            "bias": round(self.bias, 2),
            "mase": round(self.mase, 4) if self.mase is not None else None,
            "observations": self.observations,
            "unit": PRICE_UNIT,
        }


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean absolute error — the primary metric reported to users."""
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root mean squared error — penalises large misses more than MAE."""
    return float(math.sqrt(np.mean((actual - predicted) ** 2)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Mean absolute percentage error.

    Returns ``None`` when any actual value is zero: dividing by zero would make
    the metric infinite, and silently dropping those points would flatter the
    model. ``None`` is the honest answer.
    """
    if np.any(actual == 0):
        return None
    return float(np.mean(np.abs((actual - predicted) / actual)) * 100)


def bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean signed error (predicted − actual).

    Positive means the model systematically over-predicts, which matters more to
    a farmer deciding whether to sell now than a symmetric error does.
    """
    return float(np.mean(predicted - actual))


def mase(
    actual: np.ndarray,
    predicted: np.ndarray,
    training: np.ndarray,
    season_length: int = 7,
) -> float | None:
    """Mean absolute scaled error, scaled by the seasonal-naive in-sample error.

    ``MASE < 1`` means the model beats seasonal naive on this series, which is the
    single most useful number for judging whether a complex model earns its keep.
    """
    if training.size <= season_length:
        return None
    scale = float(np.mean(np.abs(training[season_length:] - training[:-season_length])))
    if scale == 0:
        return None
    return float(np.mean(np.abs(actual - predicted)) / scale)


def summarize(
    actual: np.ndarray,
    predicted: np.ndarray,
    training: np.ndarray | None = None,
    season_length: int = 7,
) -> ErrorMetrics:
    """Compute every metric for one prediction/actual pair of arrays."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError(
            f"shape mismatch: actual {actual.shape} vs predicted {predicted.shape}"
        )
    if actual.size == 0:
        raise ValueError("cannot compute metrics on empty arrays")

    return ErrorMetrics(
        mae=mae(actual, predicted),
        rmse=rmse(actual, predicted),
        mape=mape(actual, predicted),
        bias=bias(actual, predicted),
        mase=mase(actual, predicted, training, season_length) if training is not None else None,
        observations=int(actual.size),
    )


def error_by_horizon_step(
    actual: np.ndarray, predicted: np.ndarray
) -> list[dict]:
    """Per-step absolute error, so a reader can see error growth over the horizon."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    return [
        {
            "day": step + 1,
            "actual": round(float(a), 2),
            "predicted": round(float(p), 2),
            "abs_error": round(abs(float(a) - float(p)), 2),
            "signed_error": round(float(p) - float(a), 2),
        }
        for step, (a, p) in enumerate(zip(actual, predicted))
    ]
