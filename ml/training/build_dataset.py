"""Validate and clean raw price files into the processed dataset.

    python -m training.build_dataset --source datasets/raw/synthetic.csv
    python -m training.build_dataset --source datasets/raw/amis_2024.csv \\
        --source datasets/raw/amis_2025.csv

Writes ``datasets/processed/prices.parquet`` (plus a CSV copy for inspection)
and a JSON profile describing exactly what cleaning did.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from config import PROCESSED_DIR, ensure_dirs
from preprocessing.loaders import DatasetValidationError, load_price_frame

logger = logging.getLogger(__name__)

PROCESSED_FILE = PROCESSED_DIR / "prices.parquet"
PROFILE_FILE = PROCESSED_DIR / "dataset_profile.json"


def build(sources: list[Path], *, max_forward_fill_days: int = 7) -> tuple[pd.DataFrame, dict]:
    """Load, validate, clean and concatenate several source files."""
    frames: list[pd.DataFrame] = []
    per_source: list[dict] = []

    for source in sources:
        logger.info("loading %s", source)
        frame, profile = load_price_frame(source, max_forward_fill_days=max_forward_fill_days)
        profile["path"] = str(source)
        per_source.append(profile)
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    # Re-deduplicate across files: two exports may overlap in date range.
    before = len(combined)
    combined = combined.sort_values("date").drop_duplicates(
        subset=["date", "commodity", "market"], keep="last"
    )
    combined = combined.sort_values(["commodity", "market", "date"]).reset_index(drop=True)

    series_summary = (
        combined.groupby(["commodity", "market"])
        .agg(
            observations=("price_pkr", "size"),
            start=("date", "min"),
            end=("date", "max"),
            mean_pkr=("price_pkr", "mean"),
            std_pkr=("price_pkr", "std"),
            min_pkr=("price_pkr", "min"),
            max_pkr=("price_pkr", "max"),
            source=("source", lambda values: sorted(set(values))),
        )
        .reset_index()
    )
    series_summary["start"] = series_summary["start"].dt.strftime("%Y-%m-%d")
    series_summary["end"] = series_summary["end"].dt.strftime("%Y-%m-%d")
    for column in ("mean_pkr", "std_pkr", "min_pkr", "max_pkr"):
        series_summary[column] = series_summary[column].round(2)

    profile = {
        "sources": per_source,
        "rows_before_cross_file_dedup": before,
        "rows_after": len(combined),
        "cross_file_duplicates_removed": before - len(combined),
        "series": series_summary.to_dict(orient="records"),
        "data_kind": sorted(combined["source"].unique().tolist()),
        "warning": (
            "If any series has source='synthetic_fixture', this dataset is "
            "generated test data. Metrics derived from it validate the code, "
            "not real-world forecasting accuracy."
        ),
    }
    return combined, profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the processed price dataset")
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="raw CSV/parquet file (repeatable)",
    )
    parser.add_argument("--out", default=str(PROCESSED_FILE))
    parser.add_argument("--max-fill-days", type=int, default=7)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_dirs()

    try:
        frame, profile = build(
            [Path(source) for source in args.source],
            max_forward_fill_days=args.max_fill_days,
        )
    except (DatasetValidationError, FileNotFoundError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix == ".parquet":
        frame.to_parquet(destination, index=False)
        frame.to_csv(destination.with_suffix(".csv"), index=False)
    else:
        frame.to_csv(destination, index=False)
        destination.with_suffix(".parquet").parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(destination.with_suffix(".parquet"), index=False)

    PROFILE_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    print(f"wrote {destination} ({len(frame)} rows)")
    print(f"wrote {PROFILE_FILE}")
    print(f"series: {len(profile['series'])}, sources: {profile['data_kind']}")
    if "synthetic_fixture" in profile["data_kind"]:
        print(
            "\nNOTE: this dataset contains synthetic_fixture rows. Any accuracy "
            "figure computed from it validates the pipeline, not the market.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
