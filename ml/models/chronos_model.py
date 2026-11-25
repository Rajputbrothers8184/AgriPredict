"""Amazon Chronos-T5-Small adapter (zero-shot probabilistic forecasting).

What Chronos is, and what it is not
----------------------------------
Chronos is a family of pretrained transformer models that tokenise a time series
and sample future trajectories. It is used **zero-shot**: the pretrained weights
are applied to our price series without fine-tuning, because a few thousand daily
observations are not enough to fine-tune a 20M-parameter model without
over-fitting, and the project must run without a GPU.

It is explicitly **not** assumed to be the most accurate model. The evaluation
harness measures it against Seasonal Naive and XGBoost on the same rolling-origin
folds; whichever wins is reported. In several published benchmarks a seasonal
naive baseline beats foundation models on short, strongly seasonal series, and
price series in emerging markets are exactly that.

Availability and graceful degradation
-------------------------------------
Three things can be missing, and each produces a different, specific reason:

1. ``torch`` not installed                 → "PyTorch is not installed"
2. ``chronos-forecasting`` not installed   → "chronos-forecasting is not installed"
3. weights not downloadable                → the underlying error is reported

``is_available`` performs only the cheap import checks, never a network call.
Loading the pipeline is deferred until the first forecast and cached. A failure
to load is remembered so a service does not retry a 500 MB download per request.

Testing without the weights: ``ChronosForecaster(pipeline_factory=...)`` accepts
an injected factory, so the adapter's tensor handling, quantile extraction and
error paths are unit-tested with a stub pipeline.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from config import CHRONOS_DEVICE, CHRONOS_MODEL_ID, CHRONOS_NUM_SAMPLES
from models import BaseForecaster, ForecastOutput

logger = logging.getLogger(__name__)

# Chronos was trained on context windows up to 512 steps.
MAX_CONTEXT = 512
MODEL_CACHE_DIR = Path(__file__).resolve().parents[1] / ".chronos"


class ChronosUnavailable(RuntimeError):
    """Raised when Chronos cannot be used, with an actionable message."""


def _import_status() -> tuple[bool, str | None]:
    """Cheap import checks only — no network access, no weight loading."""
    try:  # pragma: no cover - environment dependent
        import torch  # noqa: F401
    except ImportError:
        return False, (
            "PyTorch is not installed. Install the CPU build with: "
            "pip install torch --index-url https://download.pytorch.org/whl/cpu"
        )

    try:  # pragma: no cover - environment dependent
        from chronos import BaseChronosPipeline  # noqa: F401
    except ImportError:
        return False, (
            "The chronos-forecasting package is not installed. "
            "Install it with: pip install -r ml/requirements-chronos.txt"
        )
    return True, None


class ChronosForecaster(BaseForecaster):
    """Zero-shot Chronos forecaster with cached pipeline loading."""

    name = "chronos"

    # Shared across instances: loading the model is the expensive step.
    _pipeline = None
    _load_error: str | None = None
    _lock = threading.Lock()

    def __init__(
        self,
        model_id: str = CHRONOS_MODEL_ID,
        device: str = CHRONOS_DEVICE,
        num_samples: int = CHRONOS_NUM_SAMPLES,
        pipeline_factory: Callable[[], object] | None = None,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.num_samples = num_samples
        self._factory = pipeline_factory
        self._last_date = None
        self._history: np.ndarray | None = None

    # ------------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        if self._factory is not None:
            return True
        available, _reason = _import_status()
        return available and ChronosForecaster._load_error is None

    @property
    def unavailable_reason(self) -> str | None:
        if self._factory is not None:
            return None
        available, reason = _import_status()
        if not available:
            return reason
        return ChronosForecaster._load_error

    # ------------------------------------------------------------------
    def _get_pipeline(self):
        """Load (once) and return the Chronos pipeline."""
        if self._factory is not None:
            return self._factory()

        with ChronosForecaster._lock:
            if ChronosForecaster._load_error is not None:
                raise ChronosUnavailable(ChronosForecaster._load_error)
            if ChronosForecaster._pipeline is not None:
                return ChronosForecaster._pipeline

            available, reason = _import_status()
            if not available:
                ChronosForecaster._load_error = reason
                raise ChronosUnavailable(reason or "Chronos is unavailable")

            from chronos import BaseChronosPipeline  # noqa: PLC0415

            try:
                MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                pipeline = BaseChronosPipeline.from_pretrained(
                    self.model_id,
                    device_map=self.device,
                    cache_dir=str(MODEL_CACHE_DIR),
                )
            except Exception as exc:  # network, disk, incompatible checkpoint…
                message = (
                    f"Could not load the Chronos weights ({self.model_id}): "
                    f"{type(exc).__name__}: {str(exc)[:300]}. "
                    "The weights are downloaded from Hugging Face on first use; "
                    "check the internet connection, or pre-download them with "
                    f"`huggingface-cli download {self.model_id}`."
                )
                ChronosForecaster._load_error = message
                raise ChronosUnavailable(message) from exc

            ChronosForecaster._pipeline = pipeline
            return pipeline

    # ------------------------------------------------------------------
    def fit(self, series: pd.Series, horizon: int = 30) -> "ChronosForecaster":
        """Chronos is zero-shot; "fitting" only records the context."""
        if len(series) < 30:
            raise ValueError(f"need at least 30 observations, got {len(series)}")
        self._history = series.to_numpy(dtype=float)[-MAX_CONTEXT:]
        self._last_date = series.index[-1].date()
        return self

    def forecast(self, series: pd.Series | None = None, horizon: int = 30) -> ForecastOutput:
        if self._history is None:
            if series is None:
                raise ValueError("call fit() first, or pass a series")
            self.fit(series, horizon)

        assert self._history is not None and self._last_date is not None
        pipeline = self._get_pipeline()

        try:
            import torch  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - stub factory path avoids this
            raise ChronosUnavailable(
                "PyTorch is required to run Chronos inference."
            ) from exc

        context = torch.tensor(self._history, dtype=torch.float32).unsqueeze(0)

        # new API (>=1.4): predict_quantiles; older API: predict with num_samples.
        if hasattr(pipeline, "predict_quantiles"):
            quantiles, mean = pipeline.predict_quantiles(
                context,
                prediction_length=horizon,
                quantile_levels=[0.1, 0.5, 0.9],
            )
            mean_array = np.asarray(mean.detach().cpu().numpy()).reshape(-1, horizon)
            quantile_array = np.asarray(quantiles.detach().cpu().numpy())
            # Shape: (batch, num_quantiles, horizon)
            q10 = quantile_array[0, 0, :]
            median = quantile_array[0, 1, :]
            q90 = quantile_array[0, 2, :]
            predictions = median
            lower = q10
            upper = q90
            _ = mean_array
        else:  # pragma: no cover - legacy chronos API
            samples = pipeline.predict(context, prediction_length=horizon, num_samples=self.num_samples)
            samples = np.asarray(samples.detach().cpu().numpy()).reshape(-1, horizon)
            predictions = np.median(samples, axis=0)
            lower = np.quantile(samples, 0.1, axis=0)
            upper = np.quantile(samples, 0.9, axis=0)

        predictions = np.clip(np.asarray(predictions, dtype=float), 0.01, None)
        lower = np.clip(np.asarray(lower, dtype=float), 0.01, None)
        upper = np.asarray(upper, dtype=float)
        # A median outside its own interval means the pipeline misbehaved; make
        # the bounds sane rather than emit a contradictory forecast.
        upper = np.maximum(upper, predictions)

        dates = [self._last_date + timedelta(days=step) for step in range(1, horizon + 1)]
        return ForecastOutput(
            model_name=self.name,
            dates=dates,
            predictions=[round(float(v), 2) for v in predictions],
            lower=[round(float(v), 2) for v in lower],
            upper=[round(float(v), 2) for v in upper],
            metadata={
                "method": "chronos_zero_shot",
                "model_id": self.model_id,
                "device": self.device,
                "context_length": int(self._history.size),
                "quantiles": [0.1, 0.9],
                "fine_tuned": False,
            },
        )


def reset_cache() -> None:
    """Drop the cached pipeline/error state (tests, or after installing weights)."""
    ChronosForecaster._pipeline = None
    ChronosForecaster._load_error = None


def availability_report() -> dict:
    """Diagnostic used by ``/models`` on the ML service and by the docs."""
    available, reason = _import_status()
    loaded = ChronosForecaster._pipeline is not None
    if available and not loaded and reason is None:
        reason = (
            "Dependencies are installed but the model weights have not been "
            "loaded yet. They are fetched from Hugging Face on first use "
            f"(`{CHRONOS_MODEL_ID}`, ~500 MB) and cached in ml/.chronos/."
        )
    return {
        "model": "chronos",
        "model_id": CHRONOS_MODEL_ID,
        "dependencies_installed": available,
        "loaded": loaded,
        "usable_now": loaded,
        "reason": reason or ChronosForecaster._load_error,
        "device": CHRONOS_DEVICE,
        "weights_present": ChronosForecaster._pipeline is not None,
        "tested": "unit tests use an injected stub pipeline; real weights were "
        "not downloadable in the build sandbox",
    }
