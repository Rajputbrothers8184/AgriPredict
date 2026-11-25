"""Pydantic schemas — the API contract.

Naming convention:

* ``XxxCreate`` / ``XxxUpdate`` — request bodies
* ``XxxRead`` — responses
* ``XxxSummary`` — compact projections used by list endpoints and dashboards

All schemas forbid unknown fields (``extra="forbid"``) so a typo in a client
payload is an explicit 422 instead of a silently ignored field.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------
Language = Literal["en", "ur"]
Theme = Literal["light", "dark", "system"]
Season = Literal["rabi", "kharif", "yearly"]
CycleStatus = Literal["planned", "active", "harvested", "failed"]
ExpenseCategory = Literal[
    "seeds",
    "fertilizer",
    "pesticide",
    "labour",
    "irrigation",
    "transport",
    "machinery",
    "other",
]
ReportType = Literal["financial_summary", "crop_cycle", "forecast"]
FileFormat = Literal["pdf", "xlsx"]

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Area = Annotated[Decimal, Field(gt=0, le=100_000, max_digits=10, decimal_places=2)]
QuantityKg = Annotated[Decimal, Field(gt=0, le=10_000_000, max_digits=12, decimal_places=2)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ORMModel(BaseModel):
    """Base for response models read from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class StrictModel(BaseModel):
    """Base for request models."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Message(BaseModel):
    message: str
    code: str | None = None


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "error"]
    ml_service: Literal["ok", "unavailable", "disabled"]


# ---------------------------------------------------------------------------
# Auth & users
# ---------------------------------------------------------------------------
class UserCreate(StrictModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: ShortText
    phone: str | None = Field(default=None, max_length=32)
    preferred_language: Language = "en"

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("phone")
    @classmethod
    def _normalise_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().replace(" ", "").replace("-", "")
        if cleaned and not cleaned.lstrip("+").isdigit():
            raise ValueError("Phone number may only contain digits, spaces, dashes and a leading +.")
        return cleaned or None


class UserLogin(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")


class RefreshRequest(StrictModel):
    refresh_token: str = Field(min_length=20, max_length=256)


class UserRead(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    preferred_language: Language
    theme: Theme
    role: str
    is_active: bool
    created_at: datetime


class UserUpdate(StrictModel):
    full_name: ShortText | None = None
    phone: str | None = Field(default=None, max_length=32)
    preferred_language: Language | None = None
    theme: Theme | None = None


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------
class FarmCreate(StrictModel):
    name: ShortText
    district: ShortText
    tehsil: str | None = Field(default=None, max_length=80)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    total_area_acres: Area | None = None

    @model_validator(mode="after")
    def _coords_together(self) -> FarmCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        return self


class FarmUpdate(StrictModel):
    name: ShortText | None = None
    district: ShortText | None = None
    tehsil: str | None = Field(default=None, max_length=80)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    total_area_acres: Area | None = None


class FarmRead(ORMModel):
    id: int
    name: str
    district: str
    tehsil: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    total_area_acres: Decimal | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------
class CommodityRead(ORMModel):
    id: int
    slug: str
    name_en: str
    name_ur: str
    category: str
    price_unit: str


class MarketRead(ORMModel):
    id: int
    slug: str
    name: str
    district: str
    province: str
    latitude: Decimal | None
    longitude: Decimal | None
    is_active: bool


# ---------------------------------------------------------------------------
# Crop cycles
# ---------------------------------------------------------------------------
class CropCycleCreate(StrictModel):
    farm_id: int = Field(gt=0)
    commodity_id: int = Field(gt=0)
    season: Season = "yearly"
    area_acres: Area
    sowing_date: date
    expected_harvest_date: date | None = None
    status: CycleStatus = "active"
    expected_yield_kg: QuantityKg | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates_in_order(self) -> CropCycleCreate:
        if self.expected_harvest_date and self.expected_harvest_date < self.sowing_date:
            raise ValueError("expected_harvest_date cannot be before sowing_date.")
        return self


class CropCycleUpdate(StrictModel):
    season: Season | None = None
    area_acres: Area | None = None
    sowing_date: date | None = None
    expected_harvest_date: date | None = None
    actual_harvest_date: date | None = None
    status: CycleStatus | None = None
    expected_yield_kg: QuantityKg | None = None
    actual_yield_kg: QuantityKg | None = None
    notes: str | None = Field(default=None, max_length=2000)


class FinanceSummary(ORMModel):
    """Derived financial projection for one crop cycle (see docs/database)."""

    revenue_pkr: Decimal
    cost_pkr: Decimal
    profit_pkr: Decimal
    margin_pct: Decimal | None
    total_yield_kg: Decimal
    break_even_price_pkr: Decimal | None
    revenue_per_acre_pkr: Decimal | None
    yield_per_acre_kg: Decimal | None


class CropCycleRead(ORMModel):
    id: int
    farm_id: int
    commodity: CommodityRead
    season: Season
    area_acres: Decimal
    sowing_date: date
    expected_harvest_date: date | None
    actual_harvest_date: date | None
    status: CycleStatus
    expected_yield_kg: Decimal | None
    actual_yield_kg: Decimal | None
    notes: str | None
    created_at: datetime


class CropCycleDetail(CropCycleRead):
    # Defaulted so the schema can validate the ORM object first and the derived
    # finance block can be attached afterwards (see routes_crops.get_cycle).
    finance: FinanceSummary | None = None


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
class ExpenseCreate(StrictModel):
    category: ExpenseCategory
    amount_pkr: Money
    expense_date: date
    description: str | None = Field(default=None, max_length=255)


class ExpenseUpdate(StrictModel):
    category: ExpenseCategory | None = None
    amount_pkr: Money | None = None
    expense_date: date | None = None
    description: str | None = Field(default=None, max_length=255)


class ExpenseRead(ORMModel):
    id: int
    crop_cycle_id: int
    category: ExpenseCategory
    amount_pkr: Decimal
    expense_date: date
    description: str | None
    created_at: datetime


class ExpenseBreakdownRow(BaseModel):
    category: ExpenseCategory
    total_pkr: Decimal
    share_pct: Decimal


# ---------------------------------------------------------------------------
# Sales
# ---------------------------------------------------------------------------
class SaleCreate(StrictModel):
    quantity_kg: QuantityKg
    unit_price_pkr: Money
    sale_date: date
    market_id: int | None = Field(default=None, gt=0)
    buyer_name: str | None = Field(default=None, max_length=120)

    # ``total_amount_pkr`` is intentionally absent: it is derived server-side.


class SaleUpdate(StrictModel):
    quantity_kg: QuantityKg | None = None
    unit_price_pkr: Money | None = None
    sale_date: date | None = None
    market_id: int | None = Field(default=None, gt=0)
    buyer_name: str | None = Field(default=None, max_length=120)


class SaleRead(ORMModel):
    id: int
    crop_cycle_id: int
    commodity_id: int
    market_id: int | None
    quantity_kg: Decimal
    unit_price_pkr: Decimal
    total_amount_pkr: Decimal
    sale_date: date
    buyer_name: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
class PricePoint(BaseModel):
    price_date: date
    min_price_pkr: Decimal | None = None
    max_price_pkr: Decimal | None = None
    avg_price_pkr: Decimal
    source: str


class PriceHistory(BaseModel):
    commodity: CommodityRead
    market: MarketRead
    unit: str = "PKR/40kg"
    points: list[PricePoint]
    count: int


class MarketComparisonRow(BaseModel):
    market: MarketRead
    latest_price_pkr: Decimal | None
    latest_date: date | None
    avg_30d_pkr: Decimal | None
    change_pct_7d: Decimal | None
    observations: int


class MarketComparison(BaseModel):
    commodity: CommodityRead
    unit: str = "PKR/40kg"
    rows: list[MarketComparisonRow]
    best_market_slug: str | None


# ---------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------
class ForecastPointRead(ORMModel):
    target_date: date
    predicted_price_pkr: Decimal
    lower_bound_pkr: Decimal | None
    upper_bound_pkr: Decimal | None


class ForecastRead(ORMModel):
    id: int
    commodity: CommodityRead
    market: MarketRead
    model_name: Literal["seasonal_naive", "xgboost", "chronos"]
    horizon_days: int
    issued_on: date
    mae: Decimal | None
    rmse: Decimal | None
    metrics: dict | None = None
    points: list[ForecastPointRead]
    is_fallback: bool = False
    disclaimer: str | None = None


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
class WeatherCurrent(BaseModel):
    farm_id: int
    observed_at: datetime
    temperature_c: Decimal | None
    humidity_pct: Decimal | None
    wind_kph: Decimal | None
    precipitation_mm: Decimal | None
    condition: str | None
    provider: Literal["openweathermap", "open-meteo", "mock"]
    is_live: bool
    note: str | None = None


class WeatherForecastDay(BaseModel):
    day: date
    temp_min_c: Decimal | None
    temp_max_c: Decimal | None
    precipitation_mm: Decimal | None
    condition: str | None


class WeatherBundle(BaseModel):
    current: WeatherCurrent
    forecast: list[WeatherForecastDay]
    provider: Literal["openweathermap", "open-meteo", "mock"]
    is_live: bool


# ---------------------------------------------------------------------------
# Buyers
# ---------------------------------------------------------------------------
class BuyerRead(ORMModel):
    id: int
    place_id: str
    name: str
    category: str
    address: str | None
    district: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    rating: Decimal | None
    user_ratings_total: int | None
    phone: str | None
    distance_km: Decimal | None = None
    fetched_at: datetime


class BuyerSearchResponse(BaseModel):
    results: list[BuyerRead]
    count: int
    radius_m: int
    source: Literal["google_places", "cache", "unavailable"]
    note: str | None = None


# ---------------------------------------------------------------------------
# Reports & finance rollups
# ---------------------------------------------------------------------------
class ReportCreate(StrictModel):
    report_type: ReportType
    file_format: FileFormat
    crop_cycle_id: int | None = Field(default=None, gt=0)
    season: Season | None = None


class ReportRead(ORMModel):
    id: int
    report_type: ReportType
    file_format: FileFormat
    filename: str
    size_bytes: int | None
    created_at: datetime
    expires_at: datetime | None
    download_url: str | None = None


class SeasonSummary(BaseModel):
    season: Season
    year: int
    cycles: int
    total_area_acres: Decimal
    revenue_pkr: Decimal
    cost_pkr: Decimal
    profit_pkr: Decimal
    margin_pct: Decimal | None
    top_expense_category: ExpenseCategory | None


class FinanceOverview(BaseModel):
    lifetime_revenue_pkr: Decimal
    lifetime_cost_pkr: Decimal
    lifetime_profit_pkr: Decimal
    margin_pct: Decimal | None
    active_cycles: int
    seasons: list[SeasonSummary]
    expense_breakdown: list[ExpenseBreakdownRow]
