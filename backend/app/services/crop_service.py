"""Crop-cycle and record services with strict per-user authorisation.

Every function takes the acting ``user_id`` and filters through the farm
ownership chain. This is the single place authorisation is enforced for farm
data, so an endpoint cannot accidentally expose another user's rows (IDOR).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Commodity, CropCycle, Expense, Farm, Market, Sale, User
from app.schemas import (
    CropCycleCreate,
    CropCycleUpdate,
    ExpenseCreate,
    ExpenseUpdate,
    FarmCreate,
    FarmUpdate,
    SaleCreate,
    SaleUpdate,
)
from app.services.finance_service import compute_sale_total


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------
def list_farms(session: Session, user_id: int) -> list[Farm]:
    return list(
        session.scalars(
            select(Farm).where(Farm.user_id == user_id).order_by(Farm.created_at.desc())
        )
    )


def get_farm(session: Session, user_id: int, farm_id: int) -> Farm:
    farm = session.scalar(select(Farm).where(Farm.id == farm_id, Farm.user_id == user_id))
    if farm is None:
        # Same error for "does not exist" and "belongs to someone else".
        raise NotFoundError("Farm not found.")
    return farm


def create_farm(session: Session, user_id: int, payload: FarmCreate) -> Farm:
    farm = Farm(
        user_id=user_id,
        name=payload.name,
        district=payload.district,
        tehsil=payload.tehsil,
        latitude=payload.latitude,
        longitude=payload.longitude,
        total_area_acres=payload.total_area_acres,
    )
    session.add(farm)
    session.commit()
    session.refresh(farm)
    return farm


def update_farm(session: Session, user_id: int, farm_id: int, payload: FarmUpdate) -> Farm:
    farm = get_farm(session, user_id, farm_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)
    session.commit()
    session.refresh(farm)
    return farm


def delete_farm(session: Session, user_id: int, farm_id: int) -> None:
    farm = get_farm(session, user_id, farm_id)
    session.delete(farm)
    session.commit()


# ---------------------------------------------------------------------------
# Crop cycles
# ---------------------------------------------------------------------------
def _cycle_query():
    return select(CropCycle).options(
        selectinload(CropCycle.commodity),
        selectinload(CropCycle.farm),
        selectinload(CropCycle.expenses),
        selectinload(CropCycle.sales),
    )


def _owned_cycle(session: Session, user_id: int, cycle_id: int) -> CropCycle:
    cycle = session.scalar(
        _cycle_query()
        .join(Farm, CropCycle.farm_id == Farm.id)
        .where(CropCycle.id == cycle_id, Farm.user_id == user_id)
    )
    if cycle is None:
        raise NotFoundError("Crop cycle not found.")
    return cycle


def list_cycles(
    session: Session,
    user_id: int,
    *,
    farm_id: int | None = None,
    status: str | None = None,
    commodity_id: int | None = None,
) -> list[CropCycle]:
    stmt = _cycle_query().join(Farm, CropCycle.farm_id == Farm.id).where(Farm.user_id == user_id)
    if farm_id is not None:
        stmt = stmt.where(CropCycle.farm_id == farm_id)
    if status is not None:
        stmt = stmt.where(CropCycle.status == status)
    if commodity_id is not None:
        stmt = stmt.where(CropCycle.commodity_id == commodity_id)
    return list(session.scalars(stmt.order_by(CropCycle.sowing_date.desc())))


def get_cycle(session: Session, user_id: int, cycle_id: int) -> CropCycle:
    return _owned_cycle(session, user_id, cycle_id)


def create_cycle(session: Session, user_id: int, payload: CropCycleCreate) -> CropCycle:
    get_farm(session, user_id, payload.farm_id)  # ownership check
    commodity = session.get(Commodity, payload.commodity_id)
    if commodity is None:
        raise ValidationError(
            "Unknown commodity.", details={"field": "commodity_id"}
        )
    cycle = CropCycle(
        farm_id=payload.farm_id,
        commodity_id=payload.commodity_id,
        season=payload.season,
        area_acres=payload.area_acres,
        sowing_date=payload.sowing_date,
        expected_harvest_date=payload.expected_harvest_date,
        status=payload.status,
        expected_yield_kg=payload.expected_yield_kg,
        notes=payload.notes,
    )
    session.add(cycle)
    session.commit()
    return _owned_cycle(session, user_id, cycle.id)


def update_cycle(
    session: Session, user_id: int, cycle_id: int, payload: CropCycleUpdate
) -> CropCycle:
    cycle = _owned_cycle(session, user_id, cycle_id)
    changes = payload.model_dump(exclude_unset=True)

    sowing = changes.get("sowing_date", cycle.sowing_date)
    harvest = changes.get("actual_harvest_date", cycle.actual_harvest_date)
    if harvest is not None and sowing is not None and harvest < sowing:
        raise ValidationError(
            "actual_harvest_date cannot be before sowing_date.",
            details={"field": "actual_harvest_date"},
        )
    expected = changes.get("expected_harvest_date", cycle.expected_harvest_date)
    if expected is not None and sowing is not None and expected < sowing:
        raise ValidationError(
            "expected_harvest_date cannot be before sowing_date.",
            details={"field": "expected_harvest_date"},
        )

    for field, value in changes.items():
        setattr(cycle, field, value)
    session.commit()
    return _owned_cycle(session, user_id, cycle_id)


def delete_cycle(session: Session, user_id: int, cycle_id: int) -> None:
    cycle = _owned_cycle(session, user_id, cycle_id)
    session.delete(cycle)
    session.commit()


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
def list_expenses(
    session: Session, user_id: int, cycle_id: int, *, category: str | None = None
) -> list[Expense]:
    _owned_cycle(session, user_id, cycle_id)
    stmt = (
        select(Expense)
        .where(Expense.crop_cycle_id == cycle_id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
    )
    if category:
        stmt = stmt.where(Expense.category == category)
    return list(session.scalars(stmt))


def create_expense(session: Session, user_id: int, cycle_id: int, payload: ExpenseCreate) -> Expense:
    _owned_cycle(session, user_id, cycle_id)
    expense = Expense(crop_cycle_id=cycle_id, **payload.model_dump())
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


def _owned_expense(session: Session, user_id: int, cycle_id: int, expense_id: int) -> Expense:
    _owned_cycle(session, user_id, cycle_id)
    expense = session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.crop_cycle_id == cycle_id)
    )
    if expense is None:
        raise NotFoundError("Expense not found.")
    return expense


def update_expense(
    session: Session, user_id: int, cycle_id: int, expense_id: int, payload: ExpenseUpdate
) -> Expense:
    expense = _owned_expense(session, user_id, cycle_id, expense_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    session.commit()
    session.refresh(expense)
    return expense


def delete_expense(session: Session, user_id: int, cycle_id: int, expense_id: int) -> None:
    expense = _owned_expense(session, user_id, cycle_id, expense_id)
    session.delete(expense)
    session.commit()


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
def list_sales(session: Session, user_id: int, cycle_id: int) -> list[Sale]:
    _owned_cycle(session, user_id, cycle_id)
    return list(
        session.scalars(
            select(Sale)
            .where(Sale.crop_cycle_id == cycle_id)
            .order_by(Sale.sale_date.desc(), Sale.id.desc())
        )
    )


def create_sale(session: Session, user_id: int, cycle_id: int, payload: SaleCreate) -> Sale:
    cycle = _owned_cycle(session, user_id, cycle_id)
    if payload.market_id is not None and session.get(Market, payload.market_id) is None:
        raise ValidationError("Unknown market.", details={"field": "market_id"})

    sale = Sale(
        crop_cycle_id=cycle.id,
        commodity_id=cycle.commodity_id,
        market_id=payload.market_id,
        quantity_kg=payload.quantity_kg,
        unit_price_pkr=payload.unit_price_pkr,
        # Derived server-side; a client-supplied total is never trusted.
        total_amount_pkr=compute_sale_total(payload.quantity_kg, payload.unit_price_pkr),
        sale_date=payload.sale_date,
        buyer_name=payload.buyer_name,
    )
    session.add(sale)

    if payload.sale_date > date.today():
        raise ValidationError(
            "sale_date cannot be in the future.", details={"field": "sale_date"}
        )
    session.commit()
    session.refresh(sale)
    return sale


def _owned_sale(session: Session, user_id: int, cycle_id: int, sale_id: int) -> Sale:
    _owned_cycle(session, user_id, cycle_id)
    sale = session.scalar(
        select(Sale).where(Sale.id == sale_id, Sale.crop_cycle_id == cycle_id)
    )
    if sale is None:
        raise NotFoundError("Sale not found.")
    return sale


def update_sale(
    session: Session, user_id: int, cycle_id: int, sale_id: int, payload: SaleUpdate
) -> Sale:
    sale = _owned_sale(session, user_id, cycle_id, sale_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sale, field, value)
    # Recompute the derived total whenever the inputs change.
    sale.total_amount_pkr = compute_sale_total(sale.quantity_kg, sale.unit_price_pkr)
    session.commit()
    session.refresh(sale)
    return sale


def delete_sale(session: Session, user_id: int, cycle_id: int, sale_id: int) -> None:
    sale = _owned_sale(session, user_id, cycle_id, sale_id)
    session.delete(sale)
    session.commit()


# ---------------------------------------------------------------------------
# Helpers used by reports/finance
# ---------------------------------------------------------------------------
def all_user_cycles(session: Session, user: User) -> list[CropCycle]:
    return list(
        session.scalars(
            _cycle_query()
            .join(Farm, CropCycle.farm_id == Farm.id)
            .where(Farm.user_id == user.id)
            .order_by(CropCycle.sowing_date.desc())
        )
    )


def sold_quantity(session: Session, cycle_id: int) -> Decimal:
    sales = list(session.scalars(select(Sale).where(Sale.crop_cycle_id == cycle_id)))
    return sum((Decimal(str(s.quantity_kg)) for s in sales), Decimal("0"))
