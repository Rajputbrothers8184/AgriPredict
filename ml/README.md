# ML — price forecasting

**Owner:** Member 3 (ML Engineer)
**Served at:** `http://localhost:8001` (a separate process from the backend)
**Consumed by:** `backend/app/services/ml_client.py`

```
ml/
├── config.py              paths, horizons, evaluation protocol, model params
├── datasets/
│   ├── raw/               downloaded source files          (git-ignored)
│   ├── processed/         cleaned parquet + profile        (git-ignored)
│   └── fixtures/          deterministic synthetic generator (committed)
├── preprocessing/
│   ├── loaders.py         schema validation, cleaning, SQL ingestion
│   └── features.py        lag/rolling/calendar features (training + inference share one impl)
├── models/
│   ├── __init__.py        BaseForecaster + ForecastOutput contract
│   ├── seasonal_naive.py  baseline + drift variant
│   ├── xgboost_model.py   direct multi-horizon XGBoost, joblib persistence
│   └── chronos_model.py   Amazon Chronos-T5-Small zero-shot adapter
├── evaluation/
│   ├── metrics.py         MAE, RMSE, MAPE, bias, MASE
│   └── backtest.py        rolling-origin evaluation (never a random split)
├── training/
│   ├── build_dataset.py   validate + clean + consolidate raw sources
│   └── train_all.py       backtest all models, save winners, write reports
├── inference/
│   ├── registry.py        model selection with a documented fallback chain
│   └── service.py         FastAPI micro-service (/predict, /health, /models)
├── saved_models/          trained artefacts (git-ignored; publish via Releases)
└── tests/                 85 tests, no network access required
```

## Quick start

```bash
cd ml
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pandas, numpy, sklearn, xgboost, fastapi
pip install -r requirements-dev.txt      # pytest

# 1. generate the labelled synthetic fixture (no downloads needed)
python -m datasets.fixtures.generate_synthetic --out datasets/raw/synthetic.csv

# 2. validate + clean it
python -m training.build_dataset --source datasets/raw/synthetic.csv

# 3. backtest every model and save the winners
python -m training.train_all --folds 3

# 4. serve predictions
uvicorn inference.service:app --port 8001
#    docs: http://localhost:8001/docs
```

## Working with real data

See [`datasets/README.md`](datasets/README.md) for the authoritative sources
(AMIS Punjab, PBS) and licensing notes. The short version:

```bash
python -m preprocessing.loaders --check path/to/amis_export.csv   # validate first
cp path/to/amis_export.csv datasets/raw/
python -m training.build_dataset --source datasets/raw/amis_export.csv
python -m training.train_all --folds 5
```

Or read the prices the backend already ingested:

```python
from preprocessing.loaders import load_from_sql, series_for
frame = load_from_sql("sqlite:///../backend/agripredict.db")
prices = series_for(frame, "wheat", "lahore-sabzi-mandi")
```

## The three models

| Model | Type | Strengths | Weaknesses |
| --- | --- | --- | --- |
| **Seasonal Naive** (+drift) | statistical baseline | always available, explainable, strong on weekly-seasonal prices | no exogenous information, flat beyond the seasonal pattern |
| **XGBoost** | direct multi-horizon gradient boosting | captures lags, momentum and annual cycles; trains in seconds on CPU | cannot extrapolate beyond the training target range; needs ~200+ days |
| **Chronos-T5-Small** | pretrained transformer, zero-shot | no training required, probabilistic output | ~500 MB weights, ~2 GB with PyTorch, no fine-tuning on our data |

**No model is assumed to be the best.** `training/train_all.py` backtests all
available models on identical rolling-origin folds and records which one won per
series and horizon. The service then loads the winning artefact.

## Evaluation protocol (why the numbers mean something)

* **Rolling-origin, expanding window.** Fold *k* trains only on data before its
  cut-off and is scored on the following 30 days. There is no shuffling, so no
  future information can leak into training.
* **Metrics in PKR per 40 kg** (maund) plus MAPE and MASE. MASE < 1 means the
  model beats seasonal naive.
* **Bias is reported** because over-prediction is worse for a farmer deciding
  whether to sell now than symmetric error.
* Full results: [`docs/ml/evaluation.md`](../docs/ml/evaluation.md).

## Chronos requirements, stated plainly

* Disk: ~2 GB (PyTorch + transformers + 500 MB weights).
* Download: the weights come from Hugging Face on first `forecast()` call and are
  cached in `ml/.chronos/`.
* Compute: CPU is sufficient (~1–3 s per 30-day forecast).
* **No paid API is used.** Hugging Face model downloads are free.
* If any of this is unavailable, the adapter raises `ChronosUnavailable` with an
  actionable message and the service returns HTTP 503 for an explicit Chronos
  request — it never silently substitutes a different model under the Chronos
  name.

## Service contract

```
GET  /health                     # is it up, and which models are usable right now?
GET  /models                     # catalogue + evaluation winners + known series
POST /predict                    # {commodity_slug, market_slug, horizon_days, history[], model}
```

`history` must be 30–3650 points, chronological, unique dates, prices > 0.
`horizon_days` must be 7 or 30. `model` ∈ `auto | seasonal_naive | xgboost | chronos`.

## Testing

```bash
cd ml && python -m pytest tests -q     # 85 tests, ~30 s, no network needed
```

Coverage highlights: schema/unit-error validation (including a per-kg/per-tonne
trap), gap filling, outlier clipping, feature/target alignment and leakage
guards, metric values checked against hand-computed numbers, the fact that fold
training windows expand, artefact save/load integrity, Chronos adapter behaviour
via an injected stub pipeline, and every `/predict` validation and failure path.

## Known limitations

1. **Accuracy on real prices is unmeasured.** No real market series was
   available in the build environment, so the recorded metrics come from the
   labelled synthetic fixture. They prove the pipeline works; they say nothing
   about real forecasting skill.
2. **Chronos with real weights is untested here.** The adapter is unit-tested
   with a stub; loading the actual checkpoint requires internet access to Hugging
   Face, which the build sandbox did not have.
3. **No exogenous features.** Weather, arrivals, fuel prices and holidays would
   plausibly improve accuracy and are not yet used.
4. **One series per model.** Models are per commodity/market; no pooling or
   hierarchical reconciliation.
5. **No fine-tuning.** Chronos is used zero-shot; fine-tuning needs more data and
   a GPU.
