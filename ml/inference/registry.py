"""Model registry: chooses and caches the forecaster for a request.

Selection policy (``model="auto"``)
-----------------------------------
1. If a trained artefact exists for (commodity, market, horizon) and its model is
   the one that won the rolling-origin backtest, use it — that is the model the
   evaluation actually justified.
2. Otherwise fit the winner class on the supplied history on the fly (XGBoost
   trains in under a second on a few thousand points).
3. If a model is unavailable or fails, fall back to Seasonal Naive with drift,
   which always works and is the benchmark. The response states which path was
   taken in ``metrics.selection_reason``.

The registry never invents a model. If nothing can produce a forecast, it raises
and the service returns a documented error.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pandas as pd

from config import HORIZONS, ML_ROOT, SAVED_MODELS_DIR
from models import BaseForecaster
from models.seasonal_naive import SeasonalNaiveDriftForecaster
from models.xgboost_model import XGBoostForecaster

logger = logging.getLogger(__name__)

EVALUATION_JSON = ML_ROOT / "reports" / "evaluation.json"


class ModelRegistry:
    """Thread-safe cache of loaded XGBoost artefacts plus the evaluation index."""

    def __init__(self, models_dir: Path = SAVED_MODELS_DIR) -> None:
        self.models_dir = Path(models_dir)
        self._cache: dict[str, XGBoostForecaster] = {}
        self._lock = threading.Lock()
        self._evaluation: dict | None = None
        self._evaluation_mtime: float = 0.0

    # ------------------------------------------------------------------
    def evaluation(self) -> dict:
        """Load ``reports/evaluation.json`` (cached, invalidated on change)."""
        if not EVALUATION_JSON.is_file():
            return {}
        mtime = EVALUATION_JSON.stat().st_mtime
        if self._evaluation is None or mtime != self._evaluation_mtime:
            try:
                self._evaluation = json.loads(EVALUATION_JSON.read_text(encoding="utf-8"))
                self._evaluation_mtime = mtime
            except json.JSONDecodeError:
                logger.warning("evaluation report is not valid JSON; ignoring it")
                self._evaluation = {}
        return self._evaluation or {}

    def winning_model(self, commodity: str, market: str, horizon: int) -> str | None:
        """The model that won the backtest for this pair/horizon, if recorded."""
        for series in self.evaluation().get("series", []):
            if series.get("commodity") == commodity and series.get("market") == market:
                comparison = series.get("horizons", {}).get(str(horizon), {})
                return comparison.get("winner")
        return None

    def artifact_path(self, commodity: str, market: str, horizon: int) -> Path | None:
        for series in self.evaluation().get("series", []):
            if series.get("commodity") == commodity and series.get("market") == market:
                artifact = series.get("artifacts", {}).get(str(horizon))
                if artifact:
                    path = self.models_dir / artifact["path"]
                    if path.is_file():
                        return path
        return None

    def known_pairs(self) -> list[dict]:
        return [
            {
                "commodity": series["commodity"],
                "market": series["market"],
                "observations": series.get("observations"),
                "horizons": sorted(series.get("horizons", {}).keys()),
                "artifacts": series.get("artifacts", {}),
            }
            for series in self.evaluation().get("series", [])
        ]

    # ------------------------------------------------------------------
    def load_xgboost(self, path: Path) -> XGBoostForecaster:
        key = str(path)
        with self._lock:
            if key not in self._cache:
                logger.info("loading XGBoost artefact %s", path)
                self._cache[key] = XGBoostForecaster.load(path)
            return self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._evaluation = None


class SelectionResult:
    """A fitted forecaster plus the reason it was chosen (for the response)."""

    __slots__ = ("forecaster", "reason", "metadata")

    def __init__(self, forecaster: BaseForecaster, reason: str, metadata: dict | None = None):
        self.forecaster = forecaster
        self.reason = reason
        self.metadata = metadata or {}


def select_forecaster(
    registry: ModelRegistry,
    *,
    commodity: str,
    market: str,
    horizon: int,
    history: pd.Series,
    requested_model: str = "auto",
) -> SelectionResult:
    """Return a fitted forecaster for the request, with a human-readable reason."""
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of {HORIZONS}")

    requested = (requested_model or "auto").lower()
    if requested not in {"auto", "seasonal_naive", "xgboost", "chronos"}:
        raise ValueError("model must be auto, seasonal_naive, xgboost or chronos")

    if requested == "seasonal_naive":
        return SelectionResult(
            SeasonalNaiveDriftForecaster().fit(history, horizon),
            "explicitly requested seasonal_naive",
        )

    if requested == "chronos":
        from models.chronos_model import ChronosForecaster, ChronosUnavailable

        forecaster = ChronosForecaster()
        if not forecaster.is_available:
            raise ChronosUnavailable(forecaster.unavailable_reason or "Chronos unavailable")
        return SelectionResult(
            forecaster.fit(history, horizon), "explicitly requested chronos"
        )

    if requested == "xgboost":
        try:
            return SelectionResult(
                XGBoostForecaster(horizon=horizon).fit(history, horizon),
                "explicitly requested xgboost",
            )
        except Exception as exc:
            logger.warning("xgboost failed (%s); falling back to seasonal naive", exc)
            return SelectionResult(
                SeasonalNaiveDriftForecaster().fit(history, horizon),
                f"xgboost failed ({type(exc).__name__}); used seasonal_naive",
                {"fallback": True},
            )

    # --- auto ---------------------------------------------------------
    winner = registry.winning_model(commodity, market, horizon)
    artifact = registry.artifact_path(commodity, market, horizon)

    if winner == "xgboost" and artifact is not None:
        try:
            model = registry.load_xgboost(artifact)
            model._last_series = history.astype(float).copy()  # refresh context
            model._last_date = history.index[-1].date()
            return SelectionResult(
                model,
                f"backtest winner for {commodity}/{market} h{horizon}; "
                f"loaded saved artefact {artifact.name}",
                {"artifact": artifact.name},
            )
        except Exception as exc:
            logger.warning("could not load artefact %s: %s", artifact, exc)

    try:
        fitted = XGBoostForecaster(horizon=horizon).fit(history, horizon)
        return SelectionResult(
            fitted,
            f"backtest winner for {commodity}/{market} h{horizon} "
            "(fitted on request because no artefact is stored)",
            {"artifact": None},
        )
    except Exception as exc:
        logger.info("xgboost unavailable for %s/%s: %s", commodity, market, exc)
        return SelectionResult(
            SeasonalNaiveDriftForecaster().fit(history, horizon),
            f"seasonal_naive benchmark (xgboost unavailable: {type(exc).__name__})",
            {"fallback": True},
        )
