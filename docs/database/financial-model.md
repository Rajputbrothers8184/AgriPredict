# Financial model

**Owner:** Member 4 (Database Engineer) — formulas agreed with Backend (Member 2)
**Implemented in:** `backend/app/services/finance_service.py`
**Exposed by:** `GET /api/v1/crop-cycles/{id}`, `GET /api/v1/finance/summary`

AgriPredict deliberately stores **only raw facts** (`expenses` and `sales`) and
derives profit/loss at read time. A stored `profit` column would have to be kept
in sync with two tables and would silently drift; a derived value cannot.

---

## Units (read this first)

| Quantity | Unit | Table.column |
| --- | --- | --- |
| Price | **PKR per 40 kg (one maund)** | `sales.unit_price_pkr`, `price_records.avg_price_pkr` |
| Quantity | **kilogram** | `sales.quantity_kg`, `crop_cycles.*_yield_kg` |
| Money total | **PKR** | `expenses.amount_pkr`, `sales.total_amount_pkr` |
| Land | **acre** | `crop_cycles.area_acres` |

The 40 kg maund is the quoting convention on Pakistani mandi boards. Mixing it
with per-kg figures is the single most likely source of a factor-of-40 error, so
every conversion happens in one place (`_kg_to_maund`).

## Formulas

Let `q` = `quantity_kg`, `p` = `unit_price_pkr`, `e` = `expense.amount_pkr`.

```
revenue(cycle)      = Σ sales.total_amount_pkr
                    = Σ (q / 40) × p                    (per sale row)

cost(cycle)         = Σ expenses.amount_pkr

profit(cycle)       = revenue − cost
margin_pct          = profit / revenue × 100          if revenue > 0 else None

total_yield_kg      = Σ sales.quantity_kg             (sold quantity)

break_even_price    = cost / (total_yield_kg / 40)    (PKR per 40 kg)
                      None when total_yield_kg == 0

yield_per_acre      = total_yield_kg / area_acres
revenue_per_acre    = revenue / area_acres
```

`margin_pct` and `break_even_price` are **`None`**, never `0`, when the
denominator is zero. The API returns `null` and the UI shows "not enough data" —
a zero would read as "break-even" and mislead the farmer.

## Rounding

- Arithmetic uses Python `decimal.Decimal`, quantised to 2 dp with
  **`ROUND_HALF_UP`** at the API boundary only. Intermediate values keep full
  precision so per-row rounding cannot accumulate.
- Percentages are quantised to 1 dp.
- `total_amount_pkr` is recomputed server-side on every write
  (`(quantity_kg / 40) × unit_price_pkr`, 2 dp). A client-supplied total is
  ignored — it is a derived column, not user input.
- Comparing floats for equality anywhere in financial code is a bug; tests
  assert with `Decimal` and a tolerance of `Decimal("0.01")`.

## Example (worked, verifiable)

A 5-acre wheat cycle:

| Fact | Value |
| --- | --- |
| Expenses | seeds 18,000 + fertilizer 42,500 + irrigation 9,000 + labour 15,000 = **84,500** |
| Sale 1 | 2,000 kg @ 3,900 PKR/maund = 50 maund × 3,900 = **195,000** |
| Sale 2 | 600 kg @ 4,050 PKR/maund = 15 maund × 4,050 = **60,750** |
| Revenue | **255,750** |
| Profit | 255,750 − 84,500 = **171,250** |
| Margin | 171,250 / 255,750 = 66.956… → **67.0 %** (1 dp, ROUND_HALF_UP) |
| Yield | 2,600 kg → 65 maund |
| Break-even price | 84,500 / 65 = **1,300.00 PKR/maund** |
| Yield per acre | **520 kg** |

This example is asserted verbatim in
`backend/tests/test_finance_service.py`.

## Aggregation rules

`GET /api/v1/finance/summary?season=rabi&year=2026` rolls up across cycles:

- Only cycles belonging to the authenticated user's farms are included.
- A cycle with expenses but no sales contributes negative profit — that is the
  correct signal (an unfinished or failed crop), not an error.
- Cycles with status `failed` are included but flagged, so the summary can show
  "excludes failed crops" as a toggle.
- Forecasts and price index are **never** included in profit — they are
  informational.

## What is intentionally not modelled

| Omitted | Reason |
| --- | --- |
| Zakat / ushr, taxes, commission (arthi) deductions | region- and contract-specific; adding a fixed rate would be wrong for most users. Recorded as a `sales` note instead. |
| Depreciation of machinery | needs asset records; out of scope for v1. |
| Labour as an hourly rate | farmers record lump sums; a rate would require timesheets. |
| Multi-currency | PKR only. |
| Inflation adjustment | would silently rewrite history. |
| Loan/credit interest | not in the approved scope. |

These are listed in `README.md` §19 as limitations rather than hidden.
