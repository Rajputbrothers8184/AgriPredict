#!/usr/bin/env python3
"""Regenerate the frontend's API contract fixture from the backend's OpenAPI schema.

Run this whenever a request/response model in ``backend/app/schemas`` changes:

    python scripts/regen_api_contract.py

Then commit the resulting ``frontend/tests/apiContract.json`` diff. That diff is
the contract change, and it is what makes a field rename visible in review
instead of turning into an empty cell on a farmer's phone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "frontend" / "tests" / "fixtures" / "apiContract.json"

# Schemas the app reads from or writes to. Extend this list when a screen starts
# depending on a new response model.
SCHEMAS = [
    # Markets and prices
    "CommodityRead",
    "MarketRead",
    "PricePoint",
    "PriceHistory",
    "MarketComparisonRow",
    "MarketComparison",
    # Forecasts
    "ForecastRead",
    "ForecastPointRead",
    # Farm ERP
    "FarmRead",
    "CropCycleRead",
    "CropCycleDetail",
    "FinanceSummary",
    "ExpenseRead",
    "SaleRead",
    # Rollups
    "FinanceOverview",
    "SeasonSummary",
    "ExpenseBreakdownRow",
    # Weather and buyers
    "WeatherBundle",
    "WeatherCurrent",
    "WeatherForecastDay",
    "BuyerRead",
    "BuyerSearchResponse",
    # Reports
    "ReportRead",
    # Request bodies
    "ExpenseCreate",
    "SaleCreate",
    "CropCycleCreate",
    "CropCycleUpdate",
    "FarmCreate",
    "ReportCreate",
]


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.main import app  # noqa: PLC0415 - import after sys.path is set

    available = app.openapi()["components"]["schemas"]
    missing = [name for name in SCHEMAS if name not in available]
    if missing:
        print(f"error: schemas not found in the OpenAPI document: {missing}", file=sys.stderr)
        return 1

    contract = {
        name: sorted(available[name].get("properties", {})) for name in SCHEMAS
    }
    CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    total_fields = sum(len(fields) for fields in contract.values())
    print(f"wrote {CONTRACT.relative_to(REPO_ROOT)}: {len(contract)} schemas, {total_fields} fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
