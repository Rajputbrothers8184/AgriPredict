"""AgriPredict ML forecasting micro-service.

    uvicorn inference.service:app --port 8001
    # docs: http://localhost:8001/docs

Deliberately separate from the main API: PyTorch, XGBoost and the model weights
never enter the backend container, and the Android app never talks to this
service directly.

Contract used by the backend (``backend/app/services/ml_client.py``)::

    POST /predict
    {
      "commodity_slug": "wheat", "market_slug": "lahore-sabzi-mandi",
      "horizon_days": 7, "model": "auto",
      "history": [{"date": "2026-11-01", "price_pkr": 3900.0}, ...]
    }
    -> {"model_name": "xgboost", "issued_on": "...",
        "points": [{"target_date": ..., "predicted_price_pkr": ...,
                    "lower_bound_pkr": ..., "upper_bound_pkr": ...}],
        "mae": 41.2, "rmse": 58.7, "metrics": {...}}
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from config import (
    DEFAULT_MODEL,
    HORIZONS,
    MAX_HISTORY_POINTS,
    SERVICE_TITLE,
    SERVICE_VERSION,
)
from inference.registry import ModelRegistry, select_forecaster
from models.chronos_model import ChronosUnavailable, availability_report
from models.xgboost_model import XGBoostForecaster

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title=SERVICE_TITLE,
    version=SERVICE_VERSION,
    description=(
        "Forecasting micro-service for AgriPredict. Serves 7- and 30-day price "
        "forecasts from Seasonal Naive, XGBoost and (when the weights are "
        "available) Amazon Chronos-T5-Small."
    ),
)
registry = ModelRegistry()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class HistoryPoint(BaseModel):
    date: date
    price_pkr: float = Field(gt=0, le=1_000_000)


class PredictRequest(BaseModel):
    commodity_slug: str = Field(min_length=1, max_length=60)
    market_slug: str = Field(min_length=1, max_length=80)
    horizon_days: int
    history: list[HistoryPoint] = Field(min_length=30, max_length=MAX_HISTORY_POINTS)
    model: Literal["auto", "seasonal_naive", "xgboost", "chronos"] = DEFAULT_MODEL

    @field_validator("horizon_days")
    @classmethod
    def _supported_horizon(cls, value: int) -> int:
        if value not in HORIZONS:
            raise ValueError(f"horizon_days must be one of {list(HORIZONS)}")
        return value

    @field_validator("history")
    @classmethod
    def _chronological(cls, points: list[HistoryPoint]) -> list[HistoryPoint]:
        dates = [point.date for point in points]
        if len(set(dates)) != len(dates):
            raise ValueError("history contains duplicate dates")
        if dates != sorted(dates):
            raise ValueError("history must be ordered oldest first")
        return points


class ForecastPointOut(BaseModel):
    target_date: date
    predicted_price_pkr: float
    lower_bound_pkr: float | None = None
    upper_bound_pkr: float | None = None


class PredictResponse(BaseModel):
    model_name: str
    issued_on: date
    points: list[ForecastPointOut]
    mae: float | None = None
    rmse: float | None = None
    metrics: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": SERVICE_TITLE,
        "version": SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness plus an honest statement of which models are actually usable."""
    chronos = availability_report()
    return {
        "status": "ok",
        "version": SERVICE_VERSION,
        "models": {
            "seasonal_naive": {"available": True},
            "xgboost": {"available": XGBoostForecaster().is_available},
            "chronos": {
                "available": bool(chronos["usable_now"]),
                "dependencies_installed": chronos["dependencies_installed"],
                "reason": chronos["reason"],
            },
        },
        "artifacts": len(registry.known_pairs()),
    }


@app.get("/models", tags=["meta"])
def models() -> dict:
    """Model catalogue, evaluation winners and known series (for the docs/UI)."""
    evaluation = registry.evaluation()
    return {
        "version": SERVICE_VERSION,
        "supported_horizons": list(HORIZONS),
        "available": {
            "seasonal_naive": True,
            "xgboost": XGBoostForecaster().is_available,
            "chronos": availability_report(),
        },
        "evaluation_generated_at": evaluation.get("generated_at"),
        "evaluation_data_sources": evaluation.get("data_sources", []),
        "known_series": registry.known_pairs(),
        "caveat": (
            "If evaluation_data_sources contains 'synthetic_fixture', the recorded "
            "metrics validate the pipeline, not real-market accuracy."
        ),
    }


@app.post("/predict", response_model=PredictResponse, tags=["forecast"])
def predict(payload: PredictRequest):
    """Forecast ``horizon_days`` ahead from the supplied history."""
    series = pd.Series(
        [point.price_pkr for point in payload.history],
        index=pd.DatetimeIndex([pd.Timestamp(point.date) for point in payload.history]),
        dtype=float,
    ).sort_index()

    try:
        selection = select_forecaster(
            registry,
            commodity=payload.commodity_slug,
            market=payload.market_slug,
            horizon=payload.horizon_days,
            history=series,
            requested_model=payload.model,
        )
    except ChronosUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "model_unavailable",
                    "message": str(exc),
                    "details": availability_report(),
                }
            },
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": str(exc)}},
        )

    forecaster = selection.forecaster
    try:
        output = forecaster.forecast(series, payload.horizon_days)
    except ChronosUnavailable as exc:
        # Weights could not be loaded (no internet, no cache). This is a
        # configuration/availability problem, not a server fault.
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "model_unavailable",
                    "message": str(exc),
                    "details": availability_report(),
                }
            },
        )
    except Exception as exc:  # a defective artefact must not 500 the service
        logger.exception("forecast failed with %s", output_name(forecaster))
        if selection.reason.startswith("auto") or "artifact" in selection.reason:
            from models.seasonal_naive import SeasonalNaiveDriftForecaster

            fallback = SeasonalNaiveDriftForecaster().fit(series, payload.horizon_days)
            output = fallback.forecast(series, payload.horizon_days)
            selection.reason += f"; fell back to seasonal_naive after {type(exc).__name__}"
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "forecast_failed",
                        "message": f"Forecasting failed: {type(exc).__name__}: {exc}",
                    }
                },
            )

    # Errors recorded by the evaluation harness for this model, if any. This is
    # a backtested figure, not a promise about the specific request.
    mae, rmse = _recorded_errors(payload)

    metrics = {
        **output.metadata,
        "selection_reason": selection.reason,
        "history_points": len(series),
        "requested_model": payload.model,
        "engine": "agripredict-ml",
    }
    metrics.update(selection.metadata)

    return PredictResponse(
        model_name=output.model_name,
        issued_on=series.index[-1].date(),
        points=[ForecastPointOut(**record) for record in output.as_records()],
        mae=mae,
        rmse=rmse,
        metrics=metrics,
    )


def output_name(forecaster) -> str:
    return getattr(forecaster, "name", type(forecaster).__name__)


def _recorded_errors(payload: PredictRequest) -> tuple[float | None, float | None]:
    """Pull the backtested MAE/RMSE for this pair/horizon from the report."""
    evaluation = registry.evaluation()
    for series in evaluation.get("series", []):
        if (
            series.get("commodity") == payload.commodity_slug
            and series.get("market") == payload.market_slug
        ):
            comparison = series.get("horizons", {}).get(str(payload.horizon_days), {})
            winner = comparison.get("winner")
            if winner and winner in comparison.get("models", {}):
                aggregate = comparison["models"][winner]["aggregate"]
                return aggregate.get("mae"), aggregate.get("rmse")
    return None, None
