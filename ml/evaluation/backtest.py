"""Rolling-origin (walk-forward) backtesting — the only honest evaluation here.

Why not a random train/test split
---------------------------------
Shuffling a time series lets the model train on tomorrow and predict yesterday.
Reported accuracy then collapses in production. This module therefore uses
**expanding-origin evaluation**: for each fold, train strictly on data up to a
cut-off, forecast the next ``horizon`` days, score against what actually
happened, then move the cut-off forward. Every prediction is out-of-sample in
time, exactly as a deployed model experiences it.

Layout::

    fold 0 : [---------- train ----------][-- test(h) --]
    fold 1 : [----------- train -----------][-- test(h) --]
    fold 2 : [------------ train ------------][-- test(h) --]
    ...

Fold 0 always trains on at least ``MIN_TRAIN_DAYS`` observations, so a short
series produces fewer folds rather than a meaningless score.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from config import BACKTEST_FOLDS, BACKTEST_HORIZON, MIN_TRAIN_DAYS
from evaluation.metrics import summarize
from models import BaseForecaster

logger = logging.getLogger(__name__)


@dataclass
class FoldResult:
    fold: int
    train_size: int
    test_start: str
    test_end: str
    predictions: list[float]
    actuals: list[float]
    metrics: dict


@dataclass
class BacktestResult:
    model_name: str
    horizon: int
    folds: list[FoldResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def aggregate(self) -> dict:
        """Average the per-fold metrics (each fold weighs equally)."""
        if not self.folds:
            return {
                "mae": None,
                "rmse": None,
                "mape_pct": None,
                "bias": None,
                "mase": None,
                "folds": 0,
                "observations": 0,
            }
        keys = ("mae", "rmse", "bias")
        aggregate: dict = {
            key: round(float(np.mean([fold.metrics[key] for fold in self.folds])), 2)
            for key in keys
        }
        mapes = [fold.metrics["mape_pct"] for fold in self.folds if fold.metrics["mape_pct"] is not None]
        mases = [fold.metrics["mase"] for fold in self.folds if fold.metrics["mase"] is not None]
        aggregate["mape_pct"] = round(float(np.mean(mapes)), 2) if mapes else None
        aggregate["mase"] = round(float(np.mean(mases)), 4) if mases else None
        aggregate["folds"] = len(self.folds)
        aggregate["observations"] = int(sum(fold.metrics["observations"] for fold in self.folds))
        return dict(sorted(aggregate.items()))

    def as_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "horizon": self.horizon,
            "aggregate": self.aggregate,
            "folds": [asdict(fold) for fold in self.folds],
            "notes": self.notes,
        }


def _fold_boundaries(n_obs: int, horizon: int, folds: int) -> list[tuple[int, int]]:
    """Compute ``(train_end, test_end)`` index pairs, oldest first.

    ``train_end`` is exclusive; ``test_end`` is exclusive. Folds are anchored so
    the final fold's test window ends on the last observation.
    """
    first_train = max(MIN_TRAIN_DAYS, n_obs - folds * horizon)
    if first_train + horizon > n_obs:
        first_train = n_obs - horizon
    if first_train < max(MIN_TRAIN_DAYS, 30):
        return []

    boundaries: list[tuple[int, int]] = []
    train_end = first_train
    while train_end + horizon <= n_obs and len(boundaries) < folds:
        boundaries.append((train_end, train_end + horizon))
        train_end += horizon
    return boundaries


def backtest_model(
    forecaster: BaseForecaster,
    series: pd.Series,
    *,
    horizon: int = BACKTEST_HORIZON,
    folds: int = BACKTEST_FOLDS,
    label: str | None = None,
) -> BacktestResult:
    """Evaluate one forecaster with expanding-origin folds.

    The forecaster is re-fitted per fold on the training window only. A model
    that cannot be fitted on a window is recorded in ``notes`` and skipped rather
    than crashing the whole comparison.
    """
    result = BacktestResult(model_name=label or forecaster.name, horizon=horizon)
    values = series.to_numpy(dtype=float)
    n_obs = values.size

    boundaries = _fold_boundaries(n_obs, horizon, folds)
    if not boundaries:
        result.notes.append(
            f"series too short for a {horizon}-day backtest: {n_obs} observations, "
            f"at least {MIN_TRAIN_DAYS + horizon} recommended"
        )
        return result

    for index, (train_end, test_end) in enumerate(boundaries):
        train = series.iloc[:train_end]
        actual_series = series.iloc[train_end:test_end]
        try:
            fitted = forecaster.fit(train, horizon)
            output = fitted.forecast(train, horizon)
        except Exception as exc:  # a model may need more history than a fold has
            result.notes.append(f"fold {index} skipped: {type(exc).__name__}: {exc}")
            logger.info("fold %s skipped for %s: %s", index, result.model_name, exc)
            continue

        predicted = np.asarray(output.predictions[: actual_series.size], dtype=float)
        actual = actual_series.to_numpy(dtype=float)[: predicted.size]
        metrics = summarize(actual, predicted, training=train.to_numpy(dtype=float))

        result.folds.append(
            FoldResult(
                fold=index,
                train_size=int(train.size),
                test_start=str(actual_series.index[0].date()),
                test_end=str(actual_series.index[-1].date()),
                predictions=[round(float(v), 2) for v in predicted],
                actuals=[round(float(v), 2) for v in actual],
                metrics=metrics.as_dict(),
            )
        )

    return result


def compare_models(
    forecasters: dict[str, BaseForecaster],
    series: pd.Series,
    *,
    horizon: int = BACKTEST_HORIZON,
    folds: int = BACKTEST_FOLDS,
) -> dict:
    """Backtest several models on identical folds and rank them by MAE.

    Ties are broken by RMSE, then by simplicity (fewer moving parts wins), so a
    baseline is never displaced by a complex model without evidence.
    """
    results: dict[str, BacktestResult] = {}
    for name, forecaster in forecasters.items():
        if not forecaster.is_available:
            skipped = BacktestResult(model_name=name, horizon=horizon)
            skipped.notes.append(f"model unavailable: {forecaster.unavailable_reason}")
            results[name] = skipped
            continue
        results[name] = backtest_model(forecaster, series, horizon=horizon, folds=folds)

    ranked = sorted(
        (
            (name, result)
            for name, result in results.items()
            if result.folds and result.aggregate["mae"] is not None
        ),
        key=lambda item: (
            item[1].aggregate["mae"],
            item[1].aggregate["rmse"] or float("inf"),
            0 if "seasonal" in item[0] else 1,
        ),
    )

    return {
        "horizon": horizon,
        "folds_requested": folds,
        "models": {name: result.as_dict() for name, result in results.items()},
        "ranking": [name for name, _result in ranked],
        "winner": ranked[0][0] if ranked else None,
        "caveat": (
            "Metrics are measured on a rolling-origin backtest of the supplied "
            "series. If that series is the synthetic fixture, these numbers show "
            "that the pipeline and the evaluation harness work — they are NOT "
            "evidence of real-market accuracy."
        ),
    }
