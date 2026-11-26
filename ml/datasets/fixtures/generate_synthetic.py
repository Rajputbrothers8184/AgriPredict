"""Deterministic synthetic price data — EXPLICITLY NOT REAL MARKET DATA.

Purpose
-------
A fresh clone must be able to run the whole pipeline (ingest → train → evaluate
→ serve) without downloading anything, and CI must be hermetic. This generator
produces series that are *structurally* realistic — trend, annual seasonality,
weekly market cycle, holiday shocks and noise — so the code paths are exercised
properly.

Every row is stamped ``source="synthetic_fixture"``, and the API/UI surface that
field. Any metric computed on this data measures **whether the code works**, not
how well AgriPredict predicts real prices. The repository never substitutes this
for observed history.

Usage::

    python -m datasets.fixtures.generate_synthetic --out datasets/raw/synthetic.csv
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    FIXTURE_COMMODITIES,
    FIXTURE_DAYS,
    FIXTURE_MARKETS,
    FIXTURE_SEED,
)

logger = logging.getLogger(__name__)

# Base price level per commodity (PKR per 40 kg) and annual amplitude. Loosely
# modelled on typical Pakistani ranges so charts look plausible — these are still
# fabricated numbers, not observations.
BASE_PROFILES = {
    "wheat": (3900.0, 0.12),
    "potato": (2200.0, 0.45),
    "onion": (2600.0, 0.55),
    "tomato": (3200.0, 0.65),
    "cotton": (6800.0, 0.18),
}
DEFAULT_PROFILE = (4000.0, 0.20)

# Markets differ by a persistent level offset and a small amount of extra noise.
MARKET_OFFSET = {
    "lahore-sabzi-mandi": 1.00,
    "multan-mandi": 0.96,
    "karachi-sabzi-mandi": 1.05,
}
DEFAULT_MARKET_OFFSET = 0.98


def generate(
    commodities: tuple[str, ...] = FIXTURE_COMMODITIES,
    markets: tuple[str, ...] = FIXTURE_MARKETS,
    days: int = FIXTURE_DAYS,
    seed: int = FIXTURE_SEED,
    end: str | None = None,
) -> pd.DataFrame:
    """Build a long-format frame: date, commodity, market, price_pkr, source."""
    rng = np.random.default_rng(seed)
    end_date = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end_date, periods=days, freq="D")
    t = np.arange(days, dtype=float)

    rows = []
    for commodity in commodities:
        base, amplitude = BASE_PROFILES.get(commodity, DEFAULT_PROFILE)
        # Annual cycle (peak slightly before harvest), weekly mandi cycle, slow
        # multi-year drift, and an AR(1)-ish noise process for realistic texture.
        annual = base * amplitude * np.sin(2 * np.pi * (t / 365.25) + rng.uniform(0, 2 * np.pi))
        weekly = base * 0.012 * np.sin(2 * np.pi * t / 7.0)
        trend = base * 0.00012 * t
        noise = np.zeros(days)
        innovation = rng.normal(0, base * 0.012, days)
        for i in range(1, days):
            noise[i] = 0.82 * noise[i - 1] + innovation[i]
        shocks = np.zeros(days)
        for _ in range(max(1, days // 120)):
            position = rng.integers(0, days - 10)
            shocks[position : position + rng.integers(2, 8)] += rng.normal(0, base * 0.06)

        level = base + annual + weekly + trend + noise + shocks
        level = np.clip(level, base * 0.35, base * 2.5)  # never absurd

        for market in markets:
            offset = MARKET_OFFSET.get(market, DEFAULT_MARKET_OFFSET)
            market_noise = rng.normal(0, base * 0.006, days)
            prices = np.clip(level * offset + market_noise, 1.0, None)
            frame = pd.DataFrame(
                {
                    "date": dates.strftime("%Y-%m-%d"),
                    "commodity": commodity,
                    "market": market,
                    "price_pkr": np.round(prices, 2),
                    "min_price_pkr": np.round(prices * 0.96, 2),
                    "max_price_pkr": np.round(prices * 1.04, 2),
                    "source": "synthetic_fixture",
                }
            )
            rows.append(frame)

    result = pd.concat(rows, ignore_index=True).sort_values(["commodity", "market", "date"])
    return result.reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate labelled synthetic price data")
    parser.add_argument("--out", default="datasets/raw/synthetic.csv")
    parser.add_argument("--days", type=int, default=FIXTURE_DAYS)
    parser.add_argument("--seed", type=int, default=FIXTURE_SEED)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    frame = generate(days=args.days, seed=args.seed)

    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)

    series = frame.groupby(["commodity", "market"]).size().size
    logger.warning(
        "Wrote %s rows across %s series to %s. "
        "This is SYNTHETIC data (source=synthetic_fixture) for pipeline testing "
        "only — it is not observed market history.",
        len(frame),
        series,
        destination,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
