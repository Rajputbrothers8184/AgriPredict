"""Farm endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas import FarmCreate, FarmRead, FarmUpdate, Message
from app.services import crop_service

router = APIRouter(prefix="/farms", tags=["farms"])


@router.get("", response_model=list[FarmRead], summary="List my farms")
def list_farms(session: DbSession, user: CurrentUser):
    return crop_service.list_farms(session, user.id)


@router.post("", response_model=FarmRead, status_code=status.HTTP_201_CREATED, summary="Add a farm")
def create_farm(payload: FarmCreate, session: DbSession, user: CurrentUser):
    return crop_service.create_farm(session, user.id, payload)


@router.get("/{farm_id}", response_model=FarmRead, summary="Get one farm")
def get_farm(farm_id: int, session: DbSession, user: CurrentUser):
    return crop_service.get_farm(session, user.id, farm_id)


@router.patch("/{farm_id}", response_model=FarmRead, summary="Update a farm")
def update_farm(farm_id: int, payload: FarmUpdate, session: DbSession, user: CurrentUser):
    return crop_service.update_farm(session, user.id, farm_id, payload)


@router.delete("/{farm_id}", response_model=Message, summary="Delete a farm and its cycles")
def delete_farm(farm_id: int, session: DbSession, user: CurrentUser) -> Message:
    crop_service.delete_farm(session, user.id, farm_id)
    return Message(message="Farm deleted.")
