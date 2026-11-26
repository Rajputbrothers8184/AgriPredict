#!/usr/bin/env python3
"""Populate the demo database with clearly-labelled synthetic price history.

Why this exists
---------------
The API needs price history before anything in the market, forecast or report
screens can show a number, and **no real Pakistani market data can be committed
to this repository** (AMIS Punjab / PBS series are not redistributable, and
inventing numbers that look like observations is not acceptable). This script
generates a *deterministic* series for demo and integration testing, and labels
every row ``source='synthetic_fixture'`` so the UI can — and does — warn the
user that the prices are simulated.

What it produces
----------------
A daily series for several commodities across several markets, with:
  * a commodity-specific base price in PKR per 40 kg (maund),
  * slow annual seasonality (harvest glut lowers prices, lean season raises them),
  * day-of-week effects — mandis are quieter on Sundays,
  * a per-market price offset, so cross-market comparison is meaningful,
  * a seeded random walk so the series is reproducible run to run.

The generator is deterministic given ``--seed``, so tests can rely on it.

Usage
-----
    cd backend
    python scripts/seed_demo_prices.py                 # 400 days, existing DB
    python scripts/seed_demo_prices.py --days 730      # two years
    python scripts/seed_demo_prices.py --reset         # delete rows first

It never touches a database containing ``source`` values other than
``synthetic_fixture`` unless ``--force`` is given, so pointing it at a database
with real prices fails loudly instead of silently mixing fabricated data in.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# Allow running as a script from backend/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Commodity, Market, PriceRecord  # noqa: E402

# Base price in PKR per 40 kg, with a plausible annual swing (PKR).
# These are order-of-magnitude anchors for a believable demo, NOT observations.
COMMODITY_PROFILE: dict[str, tuple[float, float]] = {
    "wheat": (3900.0, 350.0),
    "rice-basmati": (7200.0, 900.0),
    "cotton": (8600.0, 1200.0),
    "sugarcane": (320.0, 30.0),
    "maize": (2500.0, 320.0),
    "potato": (2100.0, 700.0),
    "onion": (1900.0, 650.0),
    "gram": (5400.0, 600.0),
    "mustard": (6100.0, 500.0),
    "mango": (9500.0, 2200.0),
}

# Markets to cover, with a location premium/discount relative to Lahore.
# A real trader compares mandis by exactly this kind of spread.
MARKET_PROFILE: dict[str, float] = {
    "lahore-sabzi-mandi": 1.000,
    "multan-mandi": 0.965,
    "faisalabad-mandi": 0.985,
    "gujranwala-mandi": 0.975,
    "sargodha-mandi": 0.955,
    "bahawalpur-mandi": 0.945,
}

DEFAULT_SEED = 20261125


def _seasonal_factor(day_of_year: int, phase: float) -> float:
    """Annual cycle in [-1, 1], shifted per commodity so peaks differ.

    Harvest arrivals depress prices; the lean season before the next harvest
    raises them. The phase offset is what stops every commodity peaking in the
    same week, which would make the demo look obviously artificial.
    """
    return math.sin(2 * math.pi * day_of_year / 365.0 + phase)


def _weekday_factor(day: date) -> float:
    """Sunday trading is thin; a small discount is realistic and testable."""
    return 0.985 if day.weekday() == 6 else 1.0


def generate_series(
    base: float,
    amplitude: float,
    market_multiplier: float,
    start: date,
    days: int,
    phase: float,
    rng: random.Random,
) -> list[tuple[date, Decimal, Decimal, Decimal]]:
    """Return [(date, min, max, avg)] for one commodity/market pair."""
    rows: list[tuple[date, Decimal, Decimal, Decimal]] = []
    # A slow random walk on top of the deterministic shape: real prices wander,
    # and a perfectly periodic series would make any model look better than it is.
    walk = 0.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        seasonal = _seasonal_factor(current.timetuple().tm_yday, phase)
        walk = walk * 0.94 + rng.gauss(0.0, 0.006)
        price = (
            (base + amplitude * seasonal)
            * market_multiplier
            * _weekday_factor(current)
            * (1.0 + walk)
        )
        # Mandi quotes are a range; the daily average sits inside it.
        spread = price * rng.uniform(0.015, 0.035)
        average = round(price, 2)
        rows.append(
            (
                current,
                Decimal(str(round(average - spread, 2))),
                Decimal(str(round(average + spread, 2))),
                Decimal(str(average)),
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=400, help="length of the series")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--end",
        default=None,
        help="last date (YYYY-MM-DD); defaults to yesterday",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete existing synthetic rows before inserting",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow writing alongside rows that are not synthetic_fixture",
    )
    parser.add_argument(
        "--commodities",
        default=",".join(COMMODITY_PROFILE),
        help="comma-separated slugs (default: all profiled commodities)",
    )
    args = parser.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    rng = random.Random(args.seed)

    with SessionLocal() as session:
        # --- safety check: never mix fabricated data into real observations ---
        non_synthetic = session.scalar(
            select(func.count())
            .select_from(PriceRecord)
            .where(PriceRecord.source != "synthetic_fixture")
        )
        if non_synthetic and not args.force:
            print(
                f"error: the database already holds {non_synthetic} price rows whose source "
                "is not 'synthetic_fixture'. Refusing to mix simulated prices into real data. "
                "Re-run with --force only if you are certain.",
                file=sys.stderr,
            )
            return 1

        if args.reset:
            removed = session.execute(
                delete(PriceRecord).where(PriceRecord.source == "synthetic_fixture")
            ).rowcount
            session.commit()
            print(f"removed {removed} existing synthetic rows")

        commodities = {c.slug: c for c in session.scalars(select(Commodity))}
        markets = {m.slug: m for m in session.scalars(select(Market))}

        wanted = [slug.strip() for slug in args.commodities.split(",") if slug.strip()]
        unknown = [slug for slug in wanted if slug not in commodities]
        if unknown:
            print(f"error: unknown commodity slugs: {unknown}", file=sys.stderr)
            return 1

        inserted = 0
        for index, slug in enumerate(wanted):
            commodity = commodities[slug]
            base, amplitude = COMMODITY_PROFILE.get(slug, (3000.0, 300.0))
            # A distinct phase per commodity keeps the demo from looking uniform.
            phase = (index / max(len(wanted), 1)) * 2 * math.pi

            for market_slug, multiplier in MARKET_PROFILE.items():
                market = markets.get(market_slug)
                if market is None:
                    print(f"  skip: market {market_slug} is not in the database")
                    continue

                existing = set(
                    session.scalars(
                        select(PriceRecord.price_date).where(
                            PriceRecord.commodity_id == commodity.id,
                            PriceRecord.market_id == market.id,
                        )
                    )
                )
                for price_date, low, high, average in generate_series(
                    base, amplitude, multiplier, start, args.days, phase, rng
                ):
                    if price_date in existing:
                        continue
                    session.add(
                        PriceRecord(
                            commodity_id=commodity.id,
                            market_id=market.id,
                            price_date=price_date,
                            min_price_pkr=low,
                            max_price_pkr=high,
                            avg_price_pkr=average,
                            source="synthetic_fixture",
                        )
                    )
                    inserted += 1
                session.flush()

            print(f"  {slug}: {len(MARKET_PROFILE)} markets x {args.days} days")

        session.commit()

        total = session.scalar(select(func.count()).select_from(PriceRecord))
        print(
            f"\ninserted {inserted} synthetic rows "
            f"({start.isoformat()} .. {end.isoformat()}); "
            f"{total} rows in price_records overall"
        )
        print(
            "every inserted row carries source='synthetic_fixture' — the API and the "
            "app show a warning banner for that source"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
