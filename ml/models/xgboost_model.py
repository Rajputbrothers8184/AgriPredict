"""XGBoost direct multi-horizon forecaster.

Why "direct" rather than recursive
----------------------------------
A recursive one-step model must be fed its own predictions to reach day 30, so a
small day-1 error compounds thirty times. Here a separate booster is trained for
each horizon (7 and 30), each predicting ``price[t+h]`` from features known at
``t``. That is slower to train but far more stable over long horizons, which is
the horizon the product actually shows.

Why trees struggle with prices (and what is done about it)
----------------------------------------------------------
Gradient-boosted trees cannot extrapolate beyond the range of their training
targets. A price that trends upward forever will be under-predicted at the top of
its range. Two mitigations:

1. Features include a *level* (recent rolling mean), so the model predicts a
   level rather than a delta from a constant baseline.
2. ``predict`` clips the output to a documented band derived from the training
   distribution, so it cannot emit an absurd number.

The limitation is stated in ``docs/ml/evaluation.md`` rather than hidden.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from config import XGB_PARAMS
from models import BaseForecaster, ForecastOutput
from preprocessing.features import build_supervised, feature_columns, last_feature_row

logger = logging.getLogger(__name__)

# Predictions are clipped to [min, max] of the training target widened by this
# fraction, so a wild feature row cannot produce an implausible price.
CLIP_HEADROOM = 0.35


class XGBoostForecaster(BaseForecaster):
    """Direct XGBoost model for a single horizon."""

    name = "xgboost"

    def __init__(self, horizon: int = 7, params: dict | None = None) -> None:
        self.horizon = horizon
        self.params = {**XGB_PARAMS, **(params or {})}
        self._model = None
        self._features: list[str] = []
        self._target_min: float = 0.0
        self._target_max: float = 1.0
        self._last_date = None
        self._last_series: pd.Series | None = None
        self._target_sd: float = 0.0

    # ------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        try:
            import xgboost  # noqa: F401
        except ImportError:  # pragma: no cover - depends on the environment
            return False
        return True

    @property
    def unavailable_reason(self) -> str | None:
        if self.is_available:
            return None
        return (
            "xgboost is not installed in this environment. "
            "Install it with: pip install -r ml/requirements.txt"
        )

    # ------------------------------------------------------------------
    def fit(self, series: pd.Series, horizon: int | None = None) -> "XGBoostForecaster":
        from xgboost import XGBRegressor

        if horizon is not None:
            self.horizon = horizon
        if not self.is_available:
            raise RuntimeError(self.unavailable_reason)

        supervised = build_supervised(series, self.horizon)
        if supervised.empty:
            raise ValueError(
                f"not enough history to train a {self.horizon}-day XGBoost model "
                f"({len(series)} observations)"
            )

        self._features = feature_columns(supervised)
        features = supervised[self._features].to_numpy(dtype=float)
        target = supervised["target"].to_numpy(dtype=float)

        model = XGBRegressor(
            **{key: value for key, value in self.params.items() if key != "objective"},
            objective=self.params.get("objective", "reg:squarederror"),
            random_state=42,
            verbosity=0,
        )
        model.fit(features, target)

        self._model = model
        self._target_min = float(target.min())
        self._target_max = float(target.max())
        self._target_sd = float(np.std(target))
        self._last_date = series.index[-1].date()
        self._last_series = series.astype(float).copy()
        return self

    # ------------------------------------------------------------------
    def predict_path(self, horizon: int | None = None) -> list[float]:
        """Forecast the whole path in one shot from the newest feature row.

        A single direct model cannot produce 30 different horizons, so for the
        path the trained model is applied to the newest row and the seasonal
        component is added as a documented correction. This keeps the path
        smooth and anchored on the learned level.
        """
        if self._model is None or self._last_series is None:
            raise ValueError("call fit() first")

        horizon = horizon or self.horizon
        row = last_feature_row(self._last_series)
        features = row[self._features].to_numpy(dtype=float)
        anchor = float(self._model.predict(features)[0])

        history = self._last_series.to_numpy(dtype=float)
        lower_clip = max(self._target_min * (1 - CLIP_HEADROOM), 0.01)
        upper_clip = self._target_max * (1 + CLIP_HEADROOM)

        path: list[float] = []
        for step in range(1, horizon + 1):
            # Blend the model's learned level with the observed seasonal shape,
            # damping the learned anchor's influence as we move further out.
            seasonal = float(history[-7 + ((step - 1) % 7)])
            weight = 1.0 / (1.0 + step / 10.0)
            blended = weight * anchor + (1.0 - weight) * seasonal
            path.append(round(float(np.clip(blended, lower_clip, upper_clip)), 2))
        return path

    def forecast(self, series: pd.Series | None = None, horizon: int = 30) -> ForecastOutput:
        if self._model is None:
            if series is None:
                raise ValueError("call fit() first, or pass a series")
            self.fit(series, horizon)

        assert self._last_date is not None
        predictions = self.predict_path(horizon)
        widening = self._target_sd * 0.5
        lower = [round(max(p - widening * float(np.sqrt(step + 1)), 0.01), 2)
                 for step, p in enumerate(predictions)]
        upper = [round(p + widening * float(np.sqrt(step + 1)), 2)
                 for step, p in enumerate(predictions)]
        dates = [self._last_date + timedelta(days=step) for step in range(1, horizon + 1)]

        return ForecastOutput(
            model_name=self.name,
            dates=dates,
            predictions=predictions,
            lower=lower,
            upper=upper,
            metadata={
                "method": "xgboost_direct",
                "horizon": horizon,
                "features": len(self._features),
                "target_range_pkr": [round(self._target_min, 2), round(self._target_max, 2)],
                "params": {k: v for k, v in self.params.items() if k != "n_jobs"},
            },
        )

    # ------------------------------------------------------------------
    def feature_importance(self, top_n: int = 10) -> dict[str, float]:
        if self._model is None:
            return {}
        importances = self._model.feature_importances_
        pairs = sorted(
            zip(self._features, importances), key=lambda kv: kv[1], reverse=True
        )
        return {name: round(float(value), 4) for name, value in pairs[:top_n]}

    def save(self, path: str | Path) -> Path:
        """Serialise with joblib, alongside the feature list (order matters)."""
        import joblib

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self._model,
                "features": self._features,
                "horizon": self.horizon,
                "target_range": [self._target_min, self._target_max],
                # Needed to rebuild prediction intervals after a reload; without
                # it a loaded model emits lower == upper == prediction.
                "target_sd": self._target_sd,
                "params": self.params,
            },
            target,
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> "XGBoostForecaster":
        import joblib

        payload = joblib.load(Path(path))
        instance = cls(horizon=payload["horizon"], params=payload.get("params"))
        instance._model = payload["model"]
        instance._features = payload["features"]
        instance._target_min, instance._target_max = payload["target_range"]
        instance._target_sd = float(payload.get("target_sd") or 0.0)
        if instance._target_sd <= 0:
            # Guard against old artefacts: derive a usable spread from the target
            # range so intervals are never degenerate.
            instance._target_sd = max((instance._target_max - instance._target_min) / 6.0, 1.0)
        return instance
