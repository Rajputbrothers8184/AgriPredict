"""Market endpoints: reference data, price history and cross-market comparison."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError
from app.schemas import (
    CommodityRead,
    MarketComparison,
    MarketRead,
    PriceHistory,
)
from app.services import market_service
from app.services.market_service import MarketDataNotFound

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/commodities", response_model=list[CommodityRead], summary="List commodities")
def list_commodities(session: DbSession):
    """Public reference data: the app needs it before the user signs in."""
    return market_service.list_commodities(session)


@router.get("/list", response_model=list[MarketRead], summary="List markets (mandis)")
def list_markets(session: DbSession, active_only: bool = Query(default=True)):
    return market_service.list_markets(session, active_only=active_only)


@router.get(
    "/history/{commodity_slug}/{market_slug}",
    response_model=PriceHistory,
    summary="Historical prices for one commodity at one market",
)
def price_history(
    commodity_slug: str,
    market_slug: str,
    session: DbSession,
    _user: CurrentUser,
    days: int = Query(default=90, ge=7, le=3650),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
):
    try:
        commodity = market_service.get_commodity_by_slug(session, commodity_slug)
        market = market_service.get_market_by_slug(session, market_slug)
    except MarketDataNotFound as exc:
        raise NotFoundError(str(exc)) from exc

    records = market_service.get_price_history(
        session, commodity.id, market.id, start=start, end=end, days=days
    )
    from app.schemas import CommodityRead, MarketRead, PricePoint  # local import: cyc-safe
    from app.services.finance_service import as_decimal

    return PriceHistory(
        commodity=CommodityRead.model_validate(commodity),
        market=MarketRead.model_validate(market),
        points=[
            PricePoint(
                price_date=r.price_date,
                min_price_pkr=r.min_price_pkr,
                max_price_pkr=r.max_price_pkr,
                avg_price_pkr=as_decimal(r.avg_price_pkr),
                source=r.source,
            )
            for r in records
        ],
        count=len(records),
    )


@router.get(
    "/compare/{commodity_slug}",
    response_model=MarketComparison,
    summary="Compare one commodity across markets",
)
def compare(
    commodity_slug: str,
    session: DbSession,
    _user: CurrentUser,
    days: int = Query(default=30, ge=7, le=365),
    district: str | None = Query(default=None, max_length=80),
):
    try:
        return market_service.compare_markets(
            session, commodity_slug, days=days, district=district
        )
    except MarketDataNotFound as exc:
        raise NotFoundError(str(exc)) from exc
