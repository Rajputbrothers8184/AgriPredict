"""Money arithmetic tests — the most important correctness tests in the backend.

The worked example from ``docs/database/financial-model.md`` is asserted verbatim
here: if the documentation and the implementation ever disagree, one of them is
wrong and this test says so.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models import CropCycle, Expense, Sale
from app.services.finance_service import (
    build_overview,
    compute_sale_total,
    expense_breakdown,
    kg_to_maund,
    round_money,
    summarise_cycle,
)


def _expense(amount: str, category: str = "seeds", day: int = 1) -> Expense:
    return Expense(
        crop_cycle_id=1,
        category=category,
        amount_pkr=Decimal(amount),
        expense_date=date(2026, 11, day),
    )


def _sale(quantity_kg: str, unit_price: str, day: int = 20) -> Sale:
    quantity = Decimal(quantity_kg)
    price = Decimal(unit_price)
    return Sale(
        crop_cycle_id=1,
        commodity_id=1,
        quantity_kg=quantity,
        unit_price_pkr=price,
        total_amount_pkr=compute_sale_total(quantity, price),
        sale_date=date(2026, 11, day),
    )


# ---------------------------------------------------------------------------
# Unit conversion and rounding
# ---------------------------------------------------------------------------
def test_kg_to_maund_uses_40kg():
    assert kg_to_maund(Decimal("40")) == Decimal("1")
    assert kg_to_maund(Decimal("2000")) == Decimal("50")
    assert kg_to_maund(Decimal("0")) == Decimal("0")


def test_round_money_uses_half_up_not_bankers():
    # 0.125 -> 0.13 with ROUND_HALF_UP; banker's rounding would give 0.12,
    # which surprises anyone reconciling a paper ledger.
    assert round_money(Decimal("0.125")) == Decimal("0.13")
    assert round_money(Decimal("0.135")) == Decimal("0.14")
    assert round_money(None) is None


@pytest.mark.parametrize(
    ("quantity_kg", "price", "expected"),
    [
        ("40", "3900", "3900.00"),        # exactly one maund
        ("2000", "3900", "195000.00"),    # 50 maunds
        ("600", "4050", "60750.00"),      # 15 maunds
        ("1200", "3333.33", "99999.90"),  # 30 maunds of a fractional price
        ("1", "1", "0.03"),               # 1 kg = 0.025 maund -> 0.03 at 2 dp
    ],
)
def test_compute_sale_total(quantity_kg: str, price: str, expected: str):
    assert compute_sale_total(Decimal(quantity_kg), Decimal(price)) == Decimal(expected)


def test_compute_sale_total_never_returns_float():
    total = compute_sale_total(Decimal("123.45"), Decimal("3999.99"))
    assert isinstance(total, Decimal)


# ---------------------------------------------------------------------------
# Cycle summary — the documented worked example
# ---------------------------------------------------------------------------
def test_documented_worked_example():
    """docs/database/financial-model.md § 'Example (worked, verifiable)'."""
    expenses = [
        _expense("18000", "seeds", 1),
        _expense("42500", "fertilizer", 2),
        _expense("9000", "irrigation", 3),
        _expense("15000", "labour", 4),
    ]
    sales = [_sale("2000", "3900", 20), _sale("600", "4050", 25)]

    summary = summarise_cycle(expenses, sales, area_acres=Decimal("5"))

    assert summary.cost_pkr == Decimal("84500.00")
    assert summary.revenue_pkr == Decimal("255750.00")
    assert summary.profit_pkr == Decimal("171250.00")
    assert summary.margin_pct == Decimal("67.0")  # 66.956% rounded to 1 dp
    assert summary.total_yield_kg == Decimal("2600.00")
    assert summary.break_even_price_pkr == Decimal("1300.00")   # 84500 / 65 maunds
    assert summary.yield_per_acre_kg == Decimal("520.00")
    assert summary.revenue_per_acre_pkr == Decimal("51150.00")


def test_no_sales_means_negative_profit_and_no_margin():
    summary = summarise_cycle([_expense("10000")], [], area_acres=Decimal("2"))
    assert summary.revenue_pkr == Decimal("0.00")
    assert summary.cost_pkr == Decimal("10000.00")
    assert summary.profit_pkr == Decimal("-10000.00")
    # A zero margin would read as "break-even" and mislead the farmer.
    assert summary.margin_pct is None
    # Nothing was sold, so break-even price is unknown, not zero.
    assert summary.break_even_price_pkr is None


def test_zero_area_does_not_divide_by_zero():
    summary = summarise_cycle([_expense("5000")], [_sale("800", "3900")], area_acres=Decimal("0"))
    assert summary.revenue_per_acre_pkr is None
    assert summary.yield_per_acre_kg is None


def test_empty_cycle_is_all_zero():
    summary = summarise_cycle([], [])
    assert summary.revenue_pkr == summary.cost_pkr == summary.profit_pkr == Decimal("0.00")
    assert summary.margin_pct is None
    assert summary.break_even_price_pkr is None


def test_float_values_from_sqlite_are_handled_exactly():
    """SQLite returns REAL; the service must not inherit binary float error."""
    expense = _expense("0.10")
    expense.amount_pkr = 0.10  # simulate a raw float from the driver
    sale = _sale("40", "0.20")
    sale.total_amount_pkr = 0.20
    summary = summarise_cycle([expense], [sale])
    assert summary.cost_pkr == Decimal("0.10")
    assert summary.revenue_pkr == Decimal("0.20")
    assert summary.profit_pkr == Decimal("0.10")


# ---------------------------------------------------------------------------
# Expense breakdown
# ---------------------------------------------------------------------------
def test_expense_breakdown_is_sorted_and_sums_to_100_percent():
    rows = expense_breakdown(
        [
            _expense("1000", "seeds"),
            _expense("3000", "fertilizer"),
            _expense("1000", "labour"),
        ]
    )
    assert [row.category for row in rows] == ["fertilizer", "seeds", "labour"]
    assert sum(row.total_pkr for row in rows) == Decimal("5000.00")
    assert sum(row.share_pct for row in rows) == pytest.approx(Decimal("100"), abs=Decimal("0.2"))


def test_expense_breakdown_of_nothing_is_empty():
    assert expense_breakdown([]) == []


# ---------------------------------------------------------------------------
# Overview / seasons
# ---------------------------------------------------------------------------
def _cycle(season: str, year: int, status: str, expenses, sales, area="5") -> CropCycle:
    cycle = CropCycle(
        farm_id=1,
        commodity_id=1,
        season=season,
        area_acres=Decimal(area),
        sowing_date=date(year, 11, 1),
        status=status,
    )
    cycle.expenses = expenses
    cycle.sales = sales
    return cycle


def test_build_overview_groups_by_season_and_counts_active():
    cycles = [
        _cycle("rabi", 2026, "active", [_expense("10000")], [_sale("2000", "3900")]),
        _cycle("kharif", 2026, "harvested", [_expense("20000")], [_sale("4000", "3600")]),
        _cycle("rabi", 2025, "failed", [_expense("5000")], []),
    ]
    overview = build_overview(cycles)

    assert overview.lifetime_cost_pkr == Decimal("35000.00")
    assert len(overview.seasons) == 3
    assert overview.active_cycles == 1
    # Seasons are newest first.
    assert overview.seasons[0].year == 2026
    assert overview.expense_breakdown[0].category == "seeds"


def test_season_summary_top_category_and_margin():
    cycles = [
        _cycle(
            "rabi",
            2026,
            "harvested",
            [_expense("1000", "seeds"), _expense("9000", "fertilizer")],
            [_sale("2000", "3900")],
        )
    ]
    season = build_overview(cycles).seasons[0]
    assert season.top_expense_category == "fertilizer"
    assert season.revenue_pkr == Decimal("195000.00")
    assert season.cost_pkr == Decimal("10000.00")
    assert season.cycles == 1
    assert season.total_area_acres == Decimal("5.00")
