"""Loading and validation of price datasets.

Everything that touches an external file passes through here, so the rest of the
pipeline can assume a clean, typed, gap-free, daily frame with a documented
schema. Validation failures are loud and name the offending row — a silently
mis-parsed file produces a model that looks fine and is meaningless.

Usage::

    from preprocessing.loaders import load_price_frame
    frame = load_price_frame("datasets/raw/amis_export.csv")

    # or from the CLI, to validate without loading:
    python -m preprocessing.loaders --check datasets/raw/amis_export.csv
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("date", "commodity", "market", "price_pkr")
OPTIONAL_COLUMNS = ("min_price_pkr", "max_price_pkr", "source")
VALID_SOURCES = {"amis_punjab", "pbs", "manual", "synthetic_fixture"}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

MIN_PRICE_PKR = 1.0          # a maund of anything costs more than one rupee
MAX_PRICE_PKR = 1_000_000.0  # absurd values indicate a unit error (per-kg vs maund)
# A per-row range check cannot detect a per-kg/per-tonne unit error, because an
# individual value of 97 or 97 000 is plausible in isolation. The *series median*
# can: no Pakistani mandi quotes a maund below ~100 PKR for a whole series.
MIN_SERIES_MEDIAN_PKR = 100.0
MAX_SERIES_MEDIAN_PKR = 60_000.0


class DatasetValidationError(ValueError):
    """Raised when a dataset cannot be trusted."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_any(path: str | Path) -> pd.DataFrame:
    """Read CSV or Parquet based on the file extension."""
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(f"dataset not found: {file}")
    if file.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(file)
    if file.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(file)
    raise DatasetValidationError(
        f"unsupported file type {file.suffix!r}; use .csv or .parquet"
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_schema(frame: pd.DataFrame, *, origin: str = "dataset") -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise DatasetValidationError(
            f"{origin}: missing required column(s) {missing}. "
            f"Expected at least {list(REQUIRED_COLUMNS)}; "
            f"optional: {list(OPTIONAL_COLUMNS)}"
        )
    if frame.empty:
        raise DatasetValidationError(f"{origin}: file contains no rows")


def validate_values(frame: pd.DataFrame, *, origin: str = "dataset") -> None:
    """Reject structural problems and physically impossible values."""
    problems: list[str] = []

    # Dates
    try:
        parsed = pd.to_datetime(frame["date"], errors="coerce", format="mixed")
    except (ValueError, TypeError) as exc:
        raise DatasetValidationError(f"{origin}: 'date' column is not parseable: {exc}") from exc
    bad_dates = parsed.isna()
    if bad_dates.any():
        rows = frame.index[bad_dates][:10].tolist()
        problems.append(f"{int(bad_dates.sum())} unparseable date(s), e.g. row indices {rows}")

    # Slugs
    for column in ("commodity", "market"):
        values = frame[column].astype(str)
        invalid = ~values.str.match(SLUG_PATTERN)
        if invalid.any():
            sample = sorted(set(values[invalid]))[:5]
            problems.append(
                f"{int(invalid.sum())} {column} value(s) are not lowercase slugs, e.g. {sample}"
            )

    # Prices
    prices = pd.to_numeric(frame["price_pkr"], errors="coerce")
    if prices.isna().any():
        problems.append(f"{int(prices.isna().sum())} non-numeric price_pkr value(s)")
    out_of_range = (prices < MIN_PRICE_PKR) | (prices > MAX_PRICE_PKR)
    if out_of_range.any():
        sample = prices[out_of_range].head(5).tolist()
        problems.append(
            f"{int(out_of_range.sum())} price_pkr value(s) outside "
            f"[{MIN_PRICE_PKR}, {MAX_PRICE_PKR}], e.g. {sample}. "
            "Prices must be PKR per 40 kg (maund), not per kg or per tonne."
        )

    if "source" in frame.columns:
        unknown = set(frame["source"].astype(str).unique()) - VALID_SOURCES
        if unknown:
            problems.append(f"unknown source value(s) {sorted(unknown)}; allowed {sorted(VALID_SOURCES)}")

    # Series-level unit check (see MIN_SERIES_MEDIAN_PKR).
    working = frame.assign(_price=prices).dropna(subset=["_price"])
    if not working.empty:
        medians = working.groupby(["commodity", "market"])["_price"].median()
        implausible_low = medians[medians < MIN_SERIES_MEDIAN_PKR]
        implausible_high = medians[medians > MAX_SERIES_MEDIAN_PKR]
        for (commodity, market), median in implausible_low.items():
            problems.append(
                f"series {commodity}/{market} has a median price of {median:,.2f} PKR, "
                f"below the plausible minimum {MIN_SERIES_MEDIAN_PKR:,.0f}. This almost "
                "always means the prices are per kilogram rather than per 40 kg maund."
            )
        for (commodity, market), median in implausible_high.items():
            problems.append(
                f"series {commodity}/{market} has a median price of {median:,.2f} PKR, "
                f"above the plausible maximum {MAX_SERIES_MEDIAN_PKR:,.0f}. This usually "
                "means the prices are per tonne rather than per 40 kg maund."
            )

    if problems:
        raise DatasetValidationError(
            f"{origin}: validation failed\n  - " + "\n  - ".join(problems)
        )


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def _flag_outliers(series: pd.Series, z_threshold: float = 4.0) -> pd.Series:
    """Boolean mask of extreme values, measured on a rolling window.

    A *global* z-score would flag genuine seasonal peaks (a tomato price spike in
    winter) as errors. A rolling window with a high threshold flags only shocks
    that are extreme relative to their own neighbourhood — typically data-entry
    slips such as an extra zero.
    """
    rolling_median = series.rolling(window=30, min_periods=7, center=True).median()
    rolling_std = series.rolling(window=30, min_periods=7, center=True).std()
    global_std = series.std() or 1.0
    deviation = (series - rolling_median.fillna(series.median())).abs()
    threshold = z_threshold * rolling_std.fillna(global_std).replace(0, global_std)
    return deviation > threshold


def clean_frame(
    frame: pd.DataFrame,
    *,
    max_forward_fill_days: int = 7,
    outlier_z: float = 4.0,
) -> tuple[pd.DataFrame, dict]:
    """Normalise dtypes, drop duplicates, impute short gaps and handle outliers.

    Returns the cleaned frame plus a profile dict describing exactly what was
    changed, so the numbers can be reported honestly rather than silently.
    """
    profile: dict = {"input_rows": len(frame)}

    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.normalize()
    work["commodity"] = work["commodity"].astype(str).str.strip().str.lower()
    work["market"] = work["market"].astype(str).str.strip().str.lower()
    work["price_pkr"] = pd.to_numeric(work["price_pkr"], errors="coerce")
    if "source" not in work.columns:
        work["source"] = "manual"

    # 1. Duplicates: keep the last report for a (date, commodity, market) quote,
    #    matching the database's uniqueness rule.
    before = len(work)
    work = work.sort_values("date").drop_duplicates(
        subset=["date", "commodity", "market"], keep="last"
    )
    profile["duplicates_removed"] = before - len(work)

    # 2. Missing prices: interpolate within a series, bounded by the fill limit.
    profile["missing_price_rows"] = int(work["price_pkr"].isna().sum())
    work = work.dropna(subset=["price_pkr"])

    cleaned_groups = []
    profile["series"] = 0
    profile["gaps_filled"] = 0
    profile["outliers_flagged"] = 0

    for (commodity, market), group in work.groupby(["commodity", "market"], sort=True):
        profile["series"] += 1
        group = group.set_index("date").sort_index()

        # 3. Reindex onto a complete daily calendar so lag features are meaningful.
        full_index = pd.date_range(group.index.min(), group.index.max(), freq="D")
        reindexed = group.reindex(full_index)
        gaps = int(reindexed["price_pkr"].isna().sum())

        # Only fill interior gaps up to the limit; do not extrapolate at the ends.
        filled = reindexed["price_pkr"].interpolate(
            method="time", limit=max_forward_fill_days, limit_direction="both"
        )
        profile["gaps_filled"] += int(filled.notna().sum() - reindexed["price_pkr"].notna().sum())
        reindexed["price_pkr"] = filled

        # 4. Outliers: flag, then clip to the local median instead of dropping the
        #    day (a dropped day would silently shift every later lag).
        outliers = _flag_outliers(reindexed["price_pkr"], outlier_z)
        if outliers.any():
            profile["outliers_flagged"] += int(outliers.sum())
            local_median = reindexed["price_pkr"].rolling(15, min_periods=3, center=True).median()
            reindexed.loc[outliers, "price_pkr"] = local_median[outliers].fillna(
                reindexed["price_pkr"].median()
            )

        reindexed["commodity"] = commodity
        reindexed["market"] = market
        reindexed["source"] = group["source"].iloc[-1] if "source" in group else "manual"
        reindexed["gap_days"] = gaps
        cleaned_groups.append(reindexed.reset_index().rename(columns={"index": "date"}))

    cleaned = pd.concat(cleaned_groups, ignore_index=True)
    cleaned = cleaned.dropna(subset=["price_pkr"]).reset_index(drop=True)
    cleaned["price_pkr"] = cleaned["price_pkr"].astype(float).round(2)

    profile["output_rows"] = len(cleaned)
    profile["date_min"] = str(cleaned["date"].min().date())
    profile["date_max"] = str(cleaned["date"].max().date())
    profile["sources"] = sorted(cleaned["source"].unique().tolist())

    return cleaned, profile


# ---------------------------------------------------------------------------
# SQL ingestion (real data path)
# ---------------------------------------------------------------------------
def load_from_sql(dsn: str, *, limit: int | None = None) -> pd.DataFrame:
    """Read ``price_records`` from the AgriPredict database into the ML schema.

    This is how real ingested prices reach the models: the ingestion job writes
    rows to ``price_records`` (with a truthful ``source``), and training reads
    them straight back. Columns are renamed to the pipeline's names.

    Requires a SQLAlchemy driver for the target database; SQLite and PostgreSQL
    are both supported.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(dsn)
    query = """
        SELECT pr.price_date            AS date,
               c.slug                   AS commodity,
               m.slug                   AS market,
               pr.avg_price_pkr         AS price_pkr,
               pr.min_price_pkr         AS min_price_pkr,
               pr.max_price_pkr         AS max_price_pkr,
               pr.source                AS source
        FROM price_records pr
        JOIN commodities c ON c.id = pr.commodity_id
        JOIN markets m     ON m.id = pr.market_id
        ORDER BY c.slug, m.slug, pr.price_date
    """
    if limit:
        query += f"\nLIMIT {int(limit)}"
    with engine.connect() as connection:
        frame = pd.read_sql(text(query), connection)
    return frame


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def load_price_frame(
    path: str | Path,
    *,
    validate_only: bool = False,
    clean: bool = True,
    max_forward_fill_days: int = 7,
) -> tuple[pd.DataFrame, dict]:
    """Load, validate and (by default) clean a dataset.

    ``max_forward_fill_days`` bounds how many consecutive missing days are
    interpolated; longer gaps are left to be dropped rather than invented.
    """
    frame = read_any(path)
    origin = str(path)
    validate_schema(frame, origin=origin)
    validate_values(frame, origin=origin)

    if validate_only:
        summary = {
            "path": origin,
            "rows": len(frame),
            "commodities": sorted(frame["commodity"].unique().tolist()),
            "markets": sorted(frame["market"].unique().tolist()),
        }
        return frame, summary

    if clean:
        return clean_frame(frame, max_forward_fill_days=max_forward_fill_days)
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame, {"input_rows": len(frame), "output_rows": len(frame)}


def series_for(frame: pd.DataFrame, commodity: str, market: str) -> pd.Series:
    """Return one series' prices indexed by date (the unit the models consume)."""
    subset = frame[(frame["commodity"] == commodity) & (frame["market"] == market)]
    if subset.empty:
        raise DatasetValidationError(f"no rows for commodity={commodity!r} market={market!r}")
    return subset.set_index("date")["price_pkr"].sort_index().astype(float)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an AgriPredict price dataset")
    parser.add_argument("--check", metavar="FILE", required=True, help="dataset to validate")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        _frame, summary = load_price_frame(args.check, validate_only=True)
    except (DatasetValidationError, FileNotFoundError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    print("VALID")
    print(f"  rows        : {summary['rows']}")
    print(f"  commodities : {', '.join(summary['commodities'])}")
    print(f"  markets     : {', '.join(summary['markets'])}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
