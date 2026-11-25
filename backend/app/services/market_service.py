"""Market price queries: history, latest quotes and cross-market comparison.

Pure query/aggregation logic with no HTTP or ORM-session management, so it can be
unit-tested against any session and reused by the report generator.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Commodity, Market, PriceRecord
from app.schemas import (
    CommodityRead,
    MarketComparison,
    MarketComparisonRow,
    MarketRead,
    PriceHistory,
    PricePoint,
)
from app.services.finance_service import as_decimal, money_or_zero, round_money, round_pct

DEFAULT_HISTORY_DAYS = 90
DEFAULT_COMPARISON_DAYS = 30


class MarketDataNotFound(LookupError):
    """Raised when a commodity or market slug does not exist."""


# ---------------------------------------------------------------------------
# Reference lookups
# ---------------------------------------------------------------------------
def get_commodity_by_slug(session: Session, slug: str) -> Commodity:
    commodity = session.scalar(select(Commodity).where(Commodity.slug == slug.lower()))
    if commodity is None:
        raise MarketDataNotFound(f"Unknown commodity slug: {slug!r}")
    return commodity


def get_market_by_slug(session: Session, slug: str) -> Market:
    market = session.scalar(select(Market).where(Market.slug == slug.lower()))
    if market is None:
        raise MarketDataNotFound(f"Unknown market slug: {slug!r}")
    return market


def list_commodities(session: Session) -> list[Commodity]:
    return list(session.scalars(select(Commodity).order_by(Commodity.name_en)))


def list_markets(session: Session, *, active_only: bool = True) -> list[Market]:
    stmt = select(Market).order_by(Market.district, Market.name)
    if active_only:
        stmt = stmt.where(Market.is_active.is_(True))
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
def get_price_history(
    session: Session,
    commodity_id: int,
    market_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    days: int = DEFAULT_HISTORY_DAYS,
) -> list[PriceRecord]:
    """Price rows for one commodity/market, oldest first (chart-ready)."""
    if end is None:
        end = session.scalar(
            select(func.max(PriceRecord.price_date)).where(
                PriceRecord.commodity_id == commodity_id,
                PriceRecord.market_id == market_id,
            )
        ) or date.today()
    if start is None:
        start = end - timedelta(days=days)

    stmt = (
        select(PriceRecord)
        .where(
            PriceRecord.commodity_id == commodity_id,
            PriceRecord.market_id == market_id,
            PriceRecord.price_date >= start,
            PriceRecord.price_date <= end,
        )
        .order_by(PriceRecord.price_date)
    )
    return list(session.scalars(stmt))


def build_price_history(
    session: Session,
    commodity_slug: str,
    market_slug: str,
    *,
    days: int = DEFAULT_HISTORY_DAYS,
) -> PriceHistory:
    commodity = get_commodity_by_slug(session, commodity_slug)
    market = get_market_by_slug(session, market_slug)
    records = get_price_history(session, commodity.id, market.id, days=days)

    return PriceHistory(
        commodity=CommodityRead.model_validate(commodity),
        market=MarketRead.model_validate(market),
        points=[
            PricePoint(
                price_date=record.price_date,
                min_price_pkr=record.min_price_pkr,
                max_price_pkr=record.max_price_pkr,
                avg_price_pkr=as_decimal(record.avg_price_pkr),
                source=record.source,
            )
            for record in records
        ],
        count=len(records),
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def _latest_and_average(
    session: Session, commodity_id: int, market_id: int, since: date
) -> tuple[PriceRecord | None, Decimal | None, int]:
    latest = session.scalar(
        select(PriceRecord)
        .where(PriceRecord.commodity_id == commodity_id, PriceRecord.market_id == market_id)
        .order_by(PriceRecord.price_date.desc())
        .limit(1)
    )
    window = list(
        session.scalars(
            select(PriceRecord)
            .where(
                PriceRecord.commodity_id == commodity_id,
                PriceRecord.market_id == market_id,
                PriceRecord.price_date >= since,
            )
            .order_by(PriceRecord.price_date.desc())
        )
    )
    if not window:
        return latest, None, 0
    average = sum((as_decimal(r.avg_price_pkr) for r in window), Decimal("0")) / len(window)
    return latest, money_or_zero(average), len(window)


def _change_pct(session: Session, commodity_id: int, market_id: int, as_of: date) -> Decimal | None:
    """Percentage change between the newest quote and the newest quote ~7 days older."""
    latest = session.scalar(
        select(PriceRecord)
        .where(PriceRecord.commodity_id == commodity_id, PriceRecord.market_id == market_id)
        .order_by(PriceRecord.price_date.desc())
        .limit(1)
    )
    if latest is None:
        return None
    reference = session.scalar(
        select(PriceRecord)
        .where(
            PriceRecord.commodity_id == commodity_id,
            PriceRecord.market_id == market_id,
            PriceRecord.price_date <= latest.price_date - timedelta(days=7),
        )
        .order_by(PriceRecord.price_date.desc())
        .limit(1)
    )
    if reference is None or as_decimal(reference.avg_price_pkr) == 0:
        return None
    change = (
        (as_decimal(latest.avg_price_pkr) - as_decimal(reference.avg_price_pkr))
        / as_decimal(reference.avg_price_pkr)
        * 100
    )
    return round_pct(change)


def compare_markets(
    session: Session,
    commodity_slug: str,
    *,
    days: int = DEFAULT_COMPARISON_DAYS,
    district: str | None = None,
) -> MarketComparison:
    """Side-by-side view of every active market for one commodity."""
    commodity = get_commodity_by_slug(session, commodity_slug)
    since = date.today() - timedelta(days=days)

    markets = list_markets(session)
    if district:
        markets = [m for m in markets if m.district.lower() == district.lower()]

    rows: list[MarketComparisonRow] = []
    for market in markets:
        latest, average, observations = _latest_and_average(
            session, commodity.id, market.id, since
        )
        if latest is None and observations == 0:
            continue  # a market with no data for this commodity is noise, not a zero
        rows.append(
            MarketComparisonRow(
                market=MarketRead.model_validate(market),
                latest_price_pkr=round_money(latest.avg_price_pkr) if latest else None,
                latest_date=latest.price_date if latest else None,
                avg_30d_pkr=average,
                change_pct_7d=_change_pct(session, commodity.id, market.id, since),
                observations=observations,
            )
        )

    rows.sort(key=lambda row: (row.latest_price_pkr is None, -(row.latest_price_pkr or 0)))
    best = rows[0].market.slug if rows else None

    return MarketComparison(
        commodity=CommodityRead.model_validate(commodity),
        rows=rows,
        best_market_slug=best,
    )


def latest_price(
    session: Session, commodity_id: int, market_id: int
) -> PriceRecord | None:
    """Newest quote for a pair — used by the forecast fallback."""
    return session.scalar(
        select(PriceRecord)
        .where(PriceRecord.commodity_id == commodity_id, PriceRecord.market_id == market_id)
        .order_by(PriceRecord.price_date.desc())
        .limit(1)
    )


def price_series(
    session: Session, commodity_id: int, market_id: int, limit: int = 180
) -> list[tuple[date, Decimal]]:
    """Most recent ``limit`` (date, avg_price) pairs, oldest first."""
    rows = list(
        session.scalars(
            select(PriceRecord)
            .where(PriceRecord.commodity_id == commodity_id, PriceRecord.market_id == market_id)
            .order_by(PriceRecord.price_date.desc())
            .limit(limit)
        )
    )
    return [(r.price_date, as_decimal(r.avg_price_pkr)) for r in reversed(rows)]
