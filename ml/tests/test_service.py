"""ML micro-service endpoints and the Chronos adapter.

Chronos is tested with an injected stub pipeline. The real weights live on
Hugging Face and were not downloadable in the build sandbox, so the adapter's
tensor handling, quantile extraction, interval sanity and error paths are what
these tests actually verify. The adapter's real-weights path is documented as
untested in docs/ml/evaluation.md rather than implied to work.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from inference.service import app, registry
from models.chronos_model import ChronosForecaster, ChronosUnavailable, availability_report

client = TestClient(app)


@pytest.fixture()
def history(seasonal_series) -> list[dict]:
    subset = seasonal_series.tail(120)
    return [
        {"date": day.strftime("%Y-%m-%d"), "price_pkr": float(value)}
        for day, value in zip(subset.index, subset.values)
    ]


def _payload(history: list[dict], **overrides) -> dict:
    body = {
        "commodity_slug": "wheat",
        "market_slug": "lahore-sabzi-mandi",
        "horizon_days": 7,
        "model": "seasonal_naive",  # deterministic and always available
        "history": history,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------
def test_root_identifies_the_service():
    body = client.get("/").json()
    assert "AgriPredict" in body["service"]
    assert body["docs"] == "/docs"


def test_health_reports_model_availability_honestly():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["models"]["seasonal_naive"]["available"] is True
    chronos = body["models"]["chronos"]
    # Whatever the environment, the answer must be explicit, not optimistic.
    assert isinstance(chronos["available"], bool)
    if not chronos["available"]:
        assert chronos["reason"], "an unavailable model must state why"


def test_models_endpoint_lists_horizons_and_caveat():
    body = client.get("/models").json()
    assert body["supported_horizons"] == [7, 30]
    assert "synthetic_fixture" in body["caveat"]


# ---------------------------------------------------------------------------
# /predict — happy paths
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("horizon", [7, 30])
def test_predict_returns_the_requested_horizon(history, horizon):
    response = client.post("/predict", json=_payload(history, horizon_days=horizon))
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["points"]) == horizon
    assert body["model_name"] == "seasonal_naive"
    dates = [point["target_date"] for point in body["points"]]
    assert dates == sorted(dates)
    assert len(set(dates)) == horizon


def test_predict_points_include_bounds(history):
    body = client.post("/predict", json=_payload(history)).json()
    for point in body["points"]:
        assert point["predicted_price_pkr"] > 0
        assert point["lower_bound_pkr"] <= point["predicted_price_pkr"]
        assert point["upper_bound_pkr"] >= point["predicted_price_pkr"]


def test_predict_returns_backtested_errors_when_known():
    """The service must report the measured error for the pair, not a guess."""
    known = registry.known_pairs()
    if not known:
        pytest.skip("no evaluation report present")
    series = known[0]
    body = {
        "commodity_slug": series["commodity"],
        "market_slug": series["market"],
        "horizon_days": 7,
        "model": "seasonal_naive",
        "history": [
            {"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "price_pkr": 3900.0 + i}
            for i in range(60)
        ],
    }
    response = client.post("/predict", json=body)
    assert response.status_code == 200
    # mae may be None if that pair/horizon was not evaluated; if present it must
    # be a non-negative number in PKR.
    payload = response.json()
    if payload["mae"] is not None:
        assert payload["mae"] >= 0


def test_predict_metrics_document_the_selection(history):
    body = client.post("/predict", json=_payload(history)).json()
    assert body["metrics"]["engine"] == "agripredict-ml"
    assert body["metrics"]["selection_reason"]
    assert body["metrics"]["history_points"] == len(history)


def test_auto_model_falls_back_gracefully_for_an_unknown_pair(history):
    """No artefact and no evaluation entry: fit on request or use the baseline."""
    response = client.post(
        "/predict",
        json=_payload(history, commodity_slug="potato", market_slug="quetta-mandi"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] in {"xgboost", "seasonal_naive"}
    assert len(body["points"]) == 7


# ---------------------------------------------------------------------------
# /predict — validation and failure paths
# ---------------------------------------------------------------------------
def test_unsupported_horizon_is_rejected(history):
    response = client.post("/predict", json=_payload(history, horizon_days=14))
    assert response.status_code == 422


def test_too_little_history_is_rejected(history):
    response = client.post("/predict", json=_payload(history[:10]))
    assert response.status_code == 422


def test_duplicate_dates_are_rejected(history):
    # Duplicate at the end, not at the start: appending history[0] would also
    # break the ordering rule and mask which validator fired.
    duplicated = history + [history[-1]]
    response = client.post("/predict", json=_payload(duplicated))
    assert response.status_code == 422
    assert "duplicate" in response.text.lower()


def test_out_of_order_history_is_rejected(history):
    response = client.post("/predict", json=_payload(list(reversed(history))))
    assert response.status_code == 422
    assert "oldest first" in response.text


def test_non_positive_price_is_rejected(history):
    broken = [dict(point) for point in history]
    broken[5]["price_pkr"] = 0
    response = client.post("/predict", json=_payload(broken))
    assert response.status_code == 422


def test_unknown_model_name_is_rejected(history):
    response = client.post("/predict", json=_payload(history, model="magic"))
    assert response.status_code == 422


def test_explicit_chronos_without_weights_returns_503_with_a_reason(history):
    """An unavailable optional model must be a clean, explained refusal."""
    if availability_report()["usable_now"]:
        pytest.skip("Chronos weights are available in this environment")
    response = client.post("/predict", json=_payload(history, model="chronos"))
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "model_unavailable"
    assert error["message"]


# ---------------------------------------------------------------------------
# Chronos adapter, exercised with a stub pipeline
# ---------------------------------------------------------------------------
class _StubTensor:
    """Minimal stand-in for a torch tensor: only .detach().cpu().numpy()."""

    def __init__(self, array: np.ndarray) -> None:
        self._array = array

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._array

    def unsqueeze(self, _dim):
        return self


class _StubPipeline:
    """Mimics the Chronos >=1.4 ``predict_quantiles`` API."""

    def __init__(self, horizon: int, base: float = 4000.0) -> None:
        self.horizon = horizon
        self.base = base
        self.calls = 0

    def predict_quantiles(self, context, prediction_length, quantile_levels):
        self.calls += 1
        horizon = prediction_length
        median = np.linspace(self.base, self.base + 70, horizon)
        q10 = median - 90
        q90 = median + 90
        quantiles = np.stack([q10, median, q90])[None, :, :]  # (1, 3, horizon)
        mean = median[None, :]
        return _StubTensor(quantiles), _StubTensor(mean)


@pytest.fixture()
def fake_torch(monkeypatch):
    """Provide a module-level ``torch`` for the adapter's tensor construction."""
    import sys
    import types

    module = types.ModuleType("torch")

    class _StubContext:
        def __init__(self, data, dtype=None):
            self.data = np.asarray(data)

        def unsqueeze(self, _dim):
            return self

    module.tensor = lambda data, dtype=None: _StubContext(data)
    module.float32 = "float32"
    monkeypatch.setitem(sys.modules, "torch", module)
    return module


def test_chronos_adapter_extracts_quantiles_from_a_stub_pipeline(seasonal_series, fake_torch):
    horizon = 14
    stub = _StubPipeline(horizon)
    forecaster = ChronosForecaster(pipeline_factory=lambda: stub)

    assert forecaster.is_available is True
    output = forecaster.fit(seasonal_series).forecast(horizon=horizon)

    assert len(output.predictions) == horizon
    assert stub.calls == 1
    assert output.model_name == "chronos"
    assert output.metadata["fine_tuned"] is False
    for lower, predicted, upper in zip(output.lower, output.predictions, output.upper):
        assert lower <= predicted <= upper
        assert predicted > 0


def test_chronos_adapter_clamps_a_negative_lower_bound(seasonal_series, fake_torch):
    class _NegativeStub(_StubPipeline):
        def predict_quantiles(self, context, prediction_length, quantile_levels):
            median = np.full(prediction_length, 50.0)
            quantiles = np.stack([median - 500, median, median + 500])[None, :, :]
            return _StubTensor(quantiles), _StubTensor(median[None, :])

    forecaster = ChronosForecaster(pipeline_factory=lambda: _NegativeStub(7))
    output = forecaster.fit(seasonal_series).forecast(horizon=7)
    assert all(value > 0 for value in output.lower)


def test_chronos_adapter_rejects_short_history():
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    forecaster = ChronosForecaster(pipeline_factory=lambda: _StubPipeline(7))
    with pytest.raises(ValueError, match="at least 30"):
        forecaster.fit(pd.Series(np.arange(10, dtype=float), index=index))


def test_chronos_adapter_reports_a_load_failure_without_crashing(seasonal_series):
    def _broken_factory():
        raise ChronosUnavailable("weights are not cached")

    forecaster = ChronosForecaster(pipeline_factory=_broken_factory)
    forecaster.fit(seasonal_series)
    with pytest.raises(ChronosUnavailable, match="weights are not cached"):
        forecaster.forecast(horizon=7)


def test_availability_report_distinguishes_deps_from_weights():
    report = availability_report()
    assert set(report) >= {
        "dependencies_installed",
        "loaded",
        "usable_now",
        "reason",
        "model_id",
    }
    # Installed dependencies alone must not be reported as usable.
    if report["dependencies_installed"] and not report["loaded"]:
        assert report["usable_now"] is False
        assert report["reason"]
