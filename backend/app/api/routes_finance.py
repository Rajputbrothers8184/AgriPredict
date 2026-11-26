"""Financial roll-up endpoints (derived, never stored)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas import ExpenseBreakdownRow, FinanceOverview, SeasonSummary
from app.services import crop_service
from app.services.finance_service import build_overview, expense_breakdown

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/summary", response_model=FinanceOverview, summary="Lifetime and per-season profit/loss")
def summary(session: DbSession, user: CurrentUser) -> FinanceOverview:
    cycles = crop_service.all_user_cycles(session, user)
    return build_overview(cycles)


@router.get(
    "/seasons", response_model=list[SeasonSummary], summary="Profit/loss grouped by season"
)
def seasons(session: DbSession, user: CurrentUser) -> list[SeasonSummary]:
    return build_overview(crop_service.all_user_cycles(session, user)).seasons


@router.get(
    "/expenses", response_model=list[ExpenseBreakdownRow], summary="Expense mix across all cycles"
)
def expenses(
    session: DbSession,
    user: CurrentUser,
    season: str | None = Query(default=None, pattern="^(rabi|kharif|yearly)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
) -> list[ExpenseBreakdownRow]:
    cycles = crop_service.all_user_cycles(session, user)
    if season:
        cycles = [c for c in cycles if c.season == season]
    if year:
        cycles = [c for c in cycles if c.sowing_date.year == year]
    return expense_breakdown([expense for cycle in cycles for expense in cycle.expenses])
