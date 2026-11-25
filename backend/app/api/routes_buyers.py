"""Buyer discovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas import BuyerRead, BuyerSearchResponse
from app.services import buyer_service, crop_service

router = APIRouter(prefix="/buyers", tags=["buyers"])


@router.get("", response_model=BuyerSearchResponse, summary="Find nearby agricultural buyers")
def search_buyers(
    session: DbSession,
    _user: CurrentUser,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    district: str | None = Query(default=None, max_length=80),
    radius_m: int | None = Query(default=None, ge=500, le=50_000),
    limit: int | None = Query(default=None, ge=1, le=20),
    cache_only: bool = Query(
        default=False, description="Never call Google; return cached buyers only"
    ),
) -> BuyerSearchResponse:
    return buyer_service.find_buyers(
        session,
        latitude=latitude,
        longitude=longitude,
        district=district,
        radius_m=radius_m,
        limit=limit,
        allow_cache_only=cache_only,
    )


@router.get("/farm/{farm_id}", response_model=BuyerSearchResponse, summary="Buyers near a farm")
def buyers_near_farm(
    farm_id: int,
    session: DbSession,
    user: CurrentUser,
    radius_m: int | None = Query(default=None, ge=500, le=50_000),
    limit: int | None = Query(default=None, ge=1, le=20),
) -> BuyerSearchResponse:
    farm = crop_service.get_farm(session, user.id, farm_id)
    return buyer_service.find_buyers(
        session,
        latitude=float(farm.latitude) if farm.latitude is not None else None,
        longitude=float(farm.longitude) if farm.longitude is not None else None,
        district=farm.district,
        radius_m=radius_m,
        limit=limit,
    )


@router.get("/saved", response_model=list[BuyerRead], summary="Previously cached buyers")
def saved_buyers(
    session: DbSession, _user: CurrentUser, limit: int = Query(default=50, ge=1, le=200)
):
    return buyer_service.list_saved_buyers(session, limit=limit)
