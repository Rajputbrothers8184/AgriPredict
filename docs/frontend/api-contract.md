# Frontend ↔ backend contract

The Android app and the FastAPI backend are separate codebases that share one
set of JSON field names. Nothing at runtime enforces that agreement: the app
reads `body.points[0].avg_price_pkr` and, if the backend renames the field,
renders "—". A farmer sees an empty price with no error anywhere.

`frontend/tests/apiContract.test.js` closes that gap.

## How it works

1. `frontend/tests/fixtures/apiContract.json` is generated **from the backend**:

   ```bash
   python scripts/regen_api_contract.py
   ```

2. The test declares, per schema, every field the app actually reads or writes.
3. It fails when a declared field is missing, naming the schema.

To add a schema to the fixture, add its name to the generator's `names` list.

## Rules that keep this test useful

* **Add the field to `READS` before you use it in a screen.** If a field is not
  listed, the test cannot protect it.
* **Never widen a schema to make the test pass.** If the app expects a field the
  backend does not send, the bug is in the app.
* Regenerate the fixture whenever the backend schemas change, and commit it —
  the diff is the contract change, which is exactly what a reviewer needs to see.

## Currently covered

| Area | Schemas |
| --- | --- |
| Markets & prices | `PricePoint`, `PriceHistory`, `MarketComparison`, `MarketComparisonRow`, `CommodityRead`, `MarketRead` |
| Forecasts | `ForecastRead`, `ForecastPointRead` |
| Farm ERP | `FarmRead`, `CropCycleRead`, `CropCycleDetail`, `FinanceSummary`, `ExpenseRead`, `SaleRead` |
| Rollups | `FinanceOverview`, `SeasonSummary`, `ExpenseBreakdownRow` |
| Weather & buyers | `WeatherBundle`, `WeatherCurrent`, `WeatherForecastDay`, `BuyerRead`, `BuyerSearchResponse` |
| Reports | `ReportRead` |
| Request bodies | `ExpenseCreate`, `SaleCreate`, `CropCycleCreate`, `CropCycleUpdate`, `FarmCreate`, `ReportCreate` |

## Confirmed by a live run

`frontend/tests/live.integration.test.js` (opt-in, `LIVE_API=1`) goes further and
checks **behaviour**: that `total_amount_pkr` is 40 000 for 400 kg at 4 000/maund,
that a signed report URL downloads a real PDF with no `Authorization` header, and
that a bogus token is rejected. Contract tests catch renames; the live suite
catches semantics.
