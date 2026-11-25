"""Train and evaluate every model, then persist the artefacts and a report.

    python -m training.train_all                       # all series, all horizons
    python -m training.train_all --horizon 7           # just the short horizon
    python -m training.train_all --series wheat:lahore-sabzi-mandi

Outputs (all git-ignored except the JSON report under docs/ when explicitly
published):

* ``ml/saved_models/<model>_<commodity>_<market>_h<horizon>.joblib``
* ``ml/reports/evaluation.json``  — full backtest detail
* ``ml/reports/evaluation.md``    — human-readable summary table

The report always states which data the numbers came from. A metric computed on
the synthetic fixture is labelled as pipeline validation, never as accuracy on
real prices.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import HORIZONS, MIN_HISTORY_DAYS, REPORTS_DIR, SAVED_MODELS_DIR, ensure_dirs
from evaluation.backtest import compare_models
from evaluation.metrics import summarize
from models.chronos_model import ChronosForecaster, availability_report
from models.seasonal_naive import SeasonalNaiveDriftForecaster
from models.xgboost_model import XGBoostForecaster
from preprocessing.loaders import series_for

logger = logging.getLogger(__name__)

PROCESSED_FILE = Path(__file__).resolve().parents[1] / "datasets" / "processed" / "prices.parquet"
EVALUATION_JSON = REPORTS_DIR / "evaluation.json"
EVALUATION_MD = REPORTS_DIR / "evaluation.md"


def default_models(horizon: int, include_chronos: bool) -> dict:
    """Model set for one horizon. Chronos is optional and never assumed."""
    models: dict = {
        "seasonal_naive": SeasonalNaiveDriftForecaster(),
        "xgboost": XGBoostForecaster(horizon=horizon),
    }
    if include_chronos:
        models["chronos"] = ChronosForecaster()
    return models


def train_and_evaluate(
    frame: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    folds: int = 3,
    include_chronos: bool = False,
    series_filter: tuple[str, str] | None = None,
) -> dict:
    """Backtest every model on every series and persist the winning artefacts."""
    ensure_dirs()
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizons": list(horizons),
        "folds": folds,
        "data_sources": sorted(frame["source"].unique().tolist()),
        "chronos": availability_report(),
        "series": [],
    }

    pairs = (
        [series_filter]
        if series_filter
        else sorted(set(zip(frame["commodity"], frame["market"])))
    )

    for commodity, market in pairs:
        prices = series_for(frame, commodity, market)
        if len(prices) < MIN_HISTORY_DAYS:
            logger.warning(
                "skipping %s/%s: %s observations < %s",
                commodity,
                market,
                len(prices),
                MIN_HISTORY_DAYS,
            )
            continue

        series_entry: dict = {
            "commodity": commodity,
            "market": market,
            "artifacts": {},
            "observations": int(len(prices)),
            "start": str(prices.index[0].date()),
            "end": str(prices.index[-1].date()),
            "horizons": {},
        }

        for horizon in horizons:
            logger.info("evaluating %s/%s horizon=%s", commodity, market, horizon)
            comparison = compare_models(
                default_models(horizon, include_chronos),
                prices,
                horizon=horizon,
                folds=folds,
            )
            series_entry["horizons"][str(horizon)] = comparison

            winner = comparison.get("winner")
            if winner in {"seasonal_naive", "xgboost"}:
                model = default_models(horizon, False)[winner]
                model.fit(prices, horizon)
                if hasattr(model, "save"):
                    path = SAVED_MODELS_DIR / f"{winner}_{commodity}_{market}_h{horizon}.joblib"
                    model.save(path)
                    series_entry["artifacts"][str(horizon)] = {
                        "model": winner,
                        "path": path.name,
                    }
                    logger.info("saved %s", path)

        report["series"].append(series_entry)

    EVALUATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    EVALUATION_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    EVALUATION_MD.parent.mkdir(parents=True, exist_ok=True)
    EVALUATION_MD.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict) -> str:
    """Render the report as a Markdown table a reviewer can read directly."""
    synthetic = "synthetic_fixture" in report["data_sources"]
    lines = [
        "# Model evaluation report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        f"**Data sources:** {', '.join(f'`{s}`' for s in report['data_sources'])}",
        "",
    ]
    if synthetic:
        lines += [
            "> **This dataset contains synthetic_fixture rows.** The figures below",
            "> validate that the pipeline, models and evaluation harness work.",
            "> They are **not** evidence of accuracy on real market prices.",
            "",
        ]

    chronos = report.get("chronos", {})
    lines += [
        "## Chronos availability",
        "",
        f"* dependencies installed: `{chronos.get('dependencies_installed')}`",
        f"* weights loaded: `{chronos.get('weights_present')}`",
        f"* reason: {chronos.get('reason') or '—'}",
        "",
    ]

    for series in report["series"]:
        lines += [
            f"## {series['commodity']} @ {series['market']}",
            "",
            f"{series['observations']} daily observations "
            f"({series['start']} → {series['end']})",
            "",
        ]
        for horizon, comparison in series["horizons"].items():
            lines += [
                f"### Horizon: {horizon} days",
                "",
                f"Rolling-origin folds: {comparison['folds_requested']} · "
                f"winner: **{comparison.get('winner') or 'no model produced a score'}**",
                "",
                "| Model | MAE (PKR/40kg) | RMSE | MAPE % | MASE | Folds | Notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for name, result in comparison["models"].items():
                aggregate = result["aggregate"]
                notes = "; ".join(result["notes"])[:80] if result["notes"] else "—"
                lines.append(
                    f"| {name} | {aggregate['mae']} | {aggregate['rmse']} | "
                    f"{aggregate['mape_pct']} | {aggregate['mase']} | "
                    f"{aggregate['folds']} | {notes} |"
                )
            lines.append("")

    lines += [
        "## Interpretation",
        "",
        "* **MAE** is in PKR per 40 kg (maund): an MAE of 90 means the forecast is",
        "  typically 90 rupees per maund away from the realised price.",
        "* **MASE < 1** means the model beats the seasonal-naive benchmark; the",
        "  benchmark is strong on strongly seasonal price series.",
        "* **Bias** (predicted − actual) shows systematic over/under-prediction; a",
        "  farmer deciding when to sell cares about direction, not just magnitude.",
        "",
        "_Caveat: metrics are computed on a rolling-origin backtest of the "
        "supplied data. On synthetic data they validate the code, not real-world "
        "accuracy._",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate AgriPredict models")
    parser.add_argument("--data", default=str(PROCESSED_FILE))
    parser.add_argument("--horizon", type=int, action="append", choices=list(HORIZONS))
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument(
        "--series",
        help="restrict to one pair, e.g. wheat:lahore-sabzi-mandi",
    )
    parser.add_argument(
        "--with-chronos",
        action="store_true",
        help="include Chronos (requires requirements-chronos.txt and the weights)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    data_path = Path(args.data)
    if not data_path.is_file():
        print(
            f"processed dataset not found: {data_path}\n"
            "Build it first:\n"
            "  python -m datasets.fixtures.generate_synthetic --out datasets/raw/synthetic.csv\n"
            "  python -m training.build_dataset --source datasets/raw/synthetic.csv",
            file=sys.stderr,
        )
        return 1

    frame = pd.read_parquet(data_path)
    series_filter = None
    if args.series:
        commodity, _, market = args.series.partition(":")
        if not market:
            print("--series must be 'commodity:market'", file=sys.stderr)
            return 2
        series_filter = (commodity, market)

    report = train_and_evaluate(
        frame,
        horizons=tuple(args.horizon) if args.horizon else HORIZONS,
        folds=args.folds,
        include_chronos=args.with_chronos,
        series_filter=series_filter,
    )
    print(f"report written to {EVALUATION_JSON}")
    print(f"markdown written to {EVALUATION_MD}")
    print(f"series evaluated: {len(report['series'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
