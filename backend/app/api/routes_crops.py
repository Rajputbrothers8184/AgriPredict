"""Crop-cycle, expense and sale endpoints.

Route layout mirrors the data model: a cycle is always addressed through its id,
and its child records through ``/crop-cycles/{id}/expenses`` etc. Ownership is
checked in the service layer for every path.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas import (
    CropCycleCreate,
    CropCycleDetail,
    CropCycleRead,
    CropCycleUpdate,
    ExpenseCreate,
    ExpenseRead,
    ExpenseUpdate,
    Message,
    SaleCreate,
    SaleRead,
    SaleUpdate,
)
from app.services import crop_service
from app.services.finance_service import summarise_cycle_orm

router = APIRouter(prefix="/crop-cycles", tags=["crops"])


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------
@router.get("", response_model=list[CropCycleRead], summary="List my crop cycles")
def list_cycles(
    session: DbSession,
    user: CurrentUser,
    farm_id: int | None = Query(default=None, gt=0),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(planned|active|harvested|failed)$"
    ),
    commodity_id: int | None = Query(default=None, gt=0),
):
    return crop_service.list_cycles(
        session, user.id, farm_id=farm_id, status=status_filter, commodity_id=commodity_id
    )


@router.post(
    "", response_model=CropCycleRead, status_code=status.HTTP_201_CREATED, summary="Start a crop cycle"
)
def create_cycle(payload: CropCycleCreate, session: DbSession, user: CurrentUser):
    return crop_service.create_cycle(session, user.id, payload)


@router.get(
    "/{cycle_id}",
    response_model=CropCycleDetail,
    summary="Get a cycle with derived profit/loss",
)
def get_cycle(cycle_id: int, session: DbSession, user: CurrentUser):
    cycle = crop_service.get_cycle(session, user.id, cycle_id)
    detail = CropCycleDetail.model_validate(cycle)
    detail.finance = summarise_cycle_orm(cycle)
    return detail


@router.patch("/{cycle_id}", response_model=CropCycleRead, summary="Update a crop cycle")
def update_cycle(cycle_id: int, payload: CropCycleUpdate, session: DbSession, user: CurrentUser):
    return crop_service.update_cycle(session, user.id, cycle_id, payload)


@router.delete("/{cycle_id}", response_model=Message, summary="Delete a cycle and its records")
def delete_cycle(cycle_id: int, session: DbSession, user: CurrentUser) -> Message:
    crop_service.delete_cycle(session, user.id, cycle_id)
    return Message(message="Crop cycle deleted.")


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
@router.get("/{cycle_id}/expenses", response_model=list[ExpenseRead], summary="List expenses")
def list_expenses(
    cycle_id: int,
    session: DbSession,
    user: CurrentUser,
    category: str | None = Query(default=None),
):
    return crop_service.list_expenses(session, user.id, cycle_id, category=category)


@router.post(
    "/{cycle_id}/expenses",
    response_model=ExpenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an expense",
)
def create_expense(
    cycle_id: int, payload: ExpenseCreate, session: DbSession, user: CurrentUser
):
    return crop_service.create_expense(session, user.id, cycle_id, payload)


@router.patch(
    "/{cycle_id}/expenses/{expense_id}", response_model=ExpenseRead, summary="Update an expense"
)
def update_expense(
    cycle_id: int,
    expense_id: int,
    payload: ExpenseUpdate,
    session: DbSession,
    user: CurrentUser,
):
    return crop_service.update_expense(session, user.id, cycle_id, expense_id, payload)


@router.delete(
    "/{cycle_id}/expenses/{expense_id}", response_model=Message, summary="Delete an expense"
)
def delete_expense(
    cycle_id: int, expense_id: int, session: DbSession, user: CurrentUser
) -> Message:
    crop_service.delete_expense(session, user.id, cycle_id, expense_id)
    return Message(message="Expense deleted.")


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
@router.get("/{cycle_id}/sales", response_model=list[SaleRead], summary="List sales")
def list_sales(cycle_id: int, session: DbSession, user: CurrentUser):
    return crop_service.list_sales(session, user.id, cycle_id)


@router.post(
    "/{cycle_id}/sales",
    response_model=SaleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a sale (total is derived server-side)",
)
def create_sale(cycle_id: int, payload: SaleCreate, session: DbSession, user: CurrentUser):
    return crop_service.create_sale(session, user.id, cycle_id, payload)


@router.patch(
    "/{cycle_id}/sales/{sale_id}", response_model=SaleRead, summary="Update a sale"
)
def update_sale(
    cycle_id: int, sale_id: int, payload: SaleUpdate, session: DbSession, user: CurrentUser
):
    return crop_service.update_sale(session, user.id, cycle_id, sale_id, payload)


@router.delete("/{cycle_id}/sales/{sale_id}", response_model=Message, summary="Delete a sale")
def delete_sale(cycle_id: int, sale_id: int, session: DbSession, user: CurrentUser) -> Message:
    crop_service.delete_sale(session, user.id, cycle_id, sale_id)
    return Message(message="Sale deleted.")
