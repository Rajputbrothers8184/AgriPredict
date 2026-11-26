"""Financial derivation — the single source of money arithmetic.

The database stores raw facts only (``expenses`` and ``sales``); profit, margin
and break-even are derived here. Keeping every formula in one module is what
makes the numbers auditable — see ``docs/database/financial-model.md`` for the
specification and a worked example that the tests assert verbatim.

Units
-----
* price  : PKR per 40 kg (one maund)   — the Pakistani mandi convention
* quantity: kilograms
* money  : PKR

All arithmetic uses ``Decimal``. Floats are never used for money in this module;
binary floating point cannot represent 0.10 exactly, and those errors accumulate
across a season of transactions.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

from app.models import CropCycle, Expense, Sale
from app.schemas import (
    ExpenseBreakdownRow,
    FinanceOverview,
    FinanceSummary,
    SeasonSummary,
)

MAUND_KG = Decimal("40")
MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.1")
ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Rounding helpers
# ---------------------------------------------------------------------------
def round_money(value: Decimal | int | float | None) -> Decimal | None:
    """Quantise to 2 dp, ROUND_HALF_UP (banker's rounding would surprise users)."""
    if value is None:
        return None
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def round_pct(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value).quantize(PCT_QUANT, rounding=ROUND_HALF_UP)


def money_or_zero(value: Decimal | int | float | str | None) -> Decimal:
    """Quantised money, defaulting to ``0.00`` for ``None``.

    Do **not** write ``round_money(value) or ZERO``: ``Decimal("0.00")`` is
    falsy, so that idiom silently returns an unquantised ``Decimal("0")`` and
    the JSON contract degrades from ``"0.00"`` to ``"0"``.
    """
    rounded = round_money(value)
    return ZERO if rounded is None else rounded


def as_decimal(value: Decimal | int | float | str | None) -> Decimal:
    """Coerce a DB value (Decimal on PostgreSQL, float on SQLite) to Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    # str() first: Decimal(float) would surface the binary representation.
    return Decimal(str(value))


def kg_to_maund(quantity_kg: Decimal) -> Decimal:
    """Convert kilograms to 40 kg maunds, the unit prices are quoted in."""
    return as_decimal(quantity_kg) / MAUND_KG


# ---------------------------------------------------------------------------
# Row-level derivation
# ---------------------------------------------------------------------------
def compute_sale_total(quantity_kg: Decimal, unit_price_pkr: Decimal) -> Decimal:
    """Total PKR for a sale: maunds × price per maund, rounded to paisa.

    Exposed because the API recomputes this server-side on every write instead of
    trusting a client-supplied total.
    """
    total = kg_to_maund(as_decimal(quantity_kg)) * as_decimal(unit_price_pkr)
    return money_or_zero(total)


def summarise_cycle(
    expenses: Sequence[Expense],
    sales: Sequence[Sale],
    area_acres: Decimal | None = None,
) -> FinanceSummary:
    """Derive revenue, cost, profit, margin, break-even and per-acre figures."""
    cost = sum((as_decimal(e.amount_pkr) for e in expenses), ZERO)
    revenue = sum((as_decimal(s.total_amount_pkr) for s in sales), ZERO)
    sold_kg = sum((as_decimal(s.quantity_kg) for s in sales), ZERO)

    profit = revenue - cost
    margin = (profit / revenue * 100) if revenue > 0 else None

    maunds_sold = kg_to_maund(sold_kg)
    break_even = (cost / maunds_sold) if maunds_sold > 0 else None

    area = as_decimal(area_acres) if area_acres is not None else ZERO
    revenue_per_acre = (revenue / area) if area > 0 else None
    yield_per_acre = (sold_kg / area) if area > 0 else None

    return FinanceSummary(
        revenue_pkr=money_or_zero(revenue),
        cost_pkr=money_or_zero(cost),
        profit_pkr=money_or_zero(profit),
        margin_pct=round_pct(margin),
        total_yield_kg=money_or_zero(sold_kg),
        break_even_price_pkr=round_money(break_even),
        revenue_per_acre_pkr=round_money(revenue_per_acre),
        yield_per_acre_kg=round_money(yield_per_acre),
    )


def summarise_cycle_orm(cycle: CropCycle) -> FinanceSummary:
    """Convenience wrapper for a loaded ``CropCycle`` with relationships."""
    return summarise_cycle(cycle.expenses, cycle.sales, cycle.area_acres)


# ---------------------------------------------------------------------------
# Aggregation across cycles
# ---------------------------------------------------------------------------
def expense_breakdown(expenses: Iterable[Expense]) -> list[ExpenseBreakdownRow]:
    """Cost per category, descending, with each category's share of total cost."""
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for expense in expenses:
        totals[expense.category] += as_decimal(expense.amount_pkr)

    grand_total = sum(totals.values(), ZERO)
    rows = [
        ExpenseBreakdownRow(
            category=category,  # type: ignore[arg-type]
            total_pkr=money_or_zero(amount),
            share_pct=money_or_zero(
                round_pct((amount / grand_total * 100) if grand_total > 0 else None)
            ),
        )
        for category, amount in totals.items()
    ]
    return sorted(rows, key=lambda row: row.total_pkr, reverse=True)


def summarise_season(
    cycles: Sequence[CropCycle], season: str, year: int
) -> SeasonSummary:
    """Roll up one season/year across the supplied cycles."""
    revenue = ZERO
    cost = ZERO
    area = ZERO
    category_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for cycle in cycles:
        for sale in cycle.sales:
            revenue += as_decimal(sale.total_amount_pkr)
        for expense in cycle.expenses:
            amount = as_decimal(expense.amount_pkr)
            cost += amount
            category_totals[expense.category] += amount
        area += as_decimal(cycle.area_acres)

    profit = revenue - cost
    margin = (profit / revenue * 100) if revenue > 0 else None
    top_category = max(category_totals.items(), key=lambda kv: kv[1])[0] if category_totals else None

    return SeasonSummary(
        season=season,  # type: ignore[arg-type]
        year=year,
        cycles=len(cycles),
        total_area_acres=money_or_zero(area),
        revenue_pkr=money_or_zero(revenue),
        cost_pkr=money_or_zero(cost),
        profit_pkr=money_or_zero(profit),
        margin_pct=round_pct(margin),
        top_expense_category=top_category,  # type: ignore[arg-type]
    )


def build_overview(cycles: Sequence[CropCycle]) -> FinanceOverview:
    """Lifetime totals, per-season summaries and the expense mix."""
    revenue = ZERO
    cost = ZERO
    all_expenses: list[Expense] = []
    grouped: dict[tuple[str, int], list[CropCycle]] = defaultdict(list)

    for cycle in cycles:
        grouped[(cycle.season, cycle.sowing_date.year)].append(cycle)
        all_expenses.extend(cycle.expenses)
        for sale in cycle.sales:
            revenue += as_decimal(sale.total_amount_pkr)
        for expense in cycle.expenses:
            cost += as_decimal(expense.amount_pkr)

    profit = revenue - cost
    seasons = [
        summarise_season(cycles_in_season, season, year)
        for (season, year), cycles_in_season in sorted(grouped.items(), reverse=True)
    ]
    active = sum(1 for cycle in cycles if cycle.status in {"planned", "active"})

    return FinanceOverview(
        lifetime_revenue_pkr=money_or_zero(revenue),
        lifetime_cost_pkr=money_or_zero(cost),
        lifetime_profit_pkr=money_or_zero(profit),
        margin_pct=round_pct((profit / revenue * 100) if revenue > 0 else None),
        active_cycles=active,
        seasons=seasons,
        expense_breakdown=expense_breakdown(all_expenses),
    )
