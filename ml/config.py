"""Central configuration for the ML pipeline.

Kept as plain module constants rather than a settings class: the ML code runs as
a CLI (training) and as a service (inference), and both must agree on the same
paths, horizons and evaluation protocol. Environment variables override only the
things a deployment genuinely needs to change.
"""

from __future__ import annotations

import os
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent
REPO_ROOT = ML_ROOT.parent

# --- Directories ----------------------------------------------------------
RAW_DIR = Path(os.getenv("ML_RAW_DIR", ML_ROOT / "datasets" / "raw"))
PROCESSED_DIR = Path(os.getenv("ML_PROCESSED_DIR", ML_ROOT / "datasets" / "processed"))
FIXTURES_DIR = ML_ROOT / "datasets" / "fixtures"
SAVED_MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", ML_ROOT / "saved_models"))
REPORTS_DIR = Path(os.getenv("ML_REPORTS_DIR", ML_ROOT / "reports"))

# --- Forecasting task -----------------------------------------------------
# The product forecasts a price index in PKR per 40 kg (one maund).
PRICE_UNIT = "PKR/40kg"
HORIZONS = (7, 30)
MIN_HISTORY_DAYS = 60          # refuse to train a series shorter than this

# --- Evaluation protocol -------------------------------------------------
# Rolling-origin (walk-forward) backtesting. NEVER a random train/test split:
# shuffling time series leaks the future into the training set and produces
# accuracy figures that cannot be reproduced in production.
BACKTEST_FOLDS = 5             # number of expanding-origin folds
BACKTEST_HORIZON = 30          # evaluate the hardest horizon on every fold
MIN_TRAIN_DAYS = 180           # first fold always trains on >= this many days

# --- XGBoost defaults ----------------------------------------------------
# Chosen to train in seconds on a laptop CPU; deliberately modest to avoid
# over-fitting a short, noisy price series.
XGB_PARAMS = {
    "n_estimators": 400,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "min_child_weight": 3,
    "reg_lambda": 1.5,
    "objective": "reg:squarederror",
    "n_jobs": int(os.getenv("XGB_N_JOBS", "4")),
}
LAG_DAYS = (1, 2, 3, 7, 14, 28)
ROLLING_WINDOWS = (7, 14, 30)

# --- Chronos -------------------------------------------------------------
CHRONOS_MODEL_ID = os.getenv("CHRONOS_MODEL_ID", "amazon/chronos-t5-small")
CHRONOS_DEVICE = os.getenv("CHRONOS_DEVICE", "cpu")
CHRONOS_NUM_SAMPLES = int(os.getenv("CHRONOS_NUM_SAMPLES", "20"))
CHRONOS_ENABLED = os.getenv("CHRONOS_ENABLED", "true").lower() in {"1", "true", "yes"}

# --- Service -------------------------------------------------------------
SERVICE_TITLE = "AgriPredict ML Forecasting Service"
SERVICE_VERSION = "0.4.0"
MAX_HISTORY_POINTS = 3650      # 10 years; guards against a client sending junk
DEFAULT_MODEL = os.getenv("ML_DEFAULT_MODEL", "auto")

# Synthetic fixture generator defaults. The fixture is EXPLICITLY test data: it
# is never presented as observed market history.
FIXTURE_SEED = 20260101
FIXTURE_DAYS = 730
FIXTURE_COMMODITIES = ("wheat", "potato", "onion")
FIXTURE_MARKETS = ("lahore-sabzi-mandi", "multan-mandi")


def ensure_dirs() -> None:
    for directory in (RAW_DIR, PROCESSED_DIR, SAVED_MODELS_DIR, REPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
