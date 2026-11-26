# Schema reference

Canonical DDL: [`001_schema.sql`](001_schema.sql). Data model diagram:
[`../diagrams/erd.md`](../diagrams/erd.md).

Money columns are **PKR**; price columns are **PKR per 40 kg (maund)**;
quantities are **kilograms**. TIMESTAMPTZ everywhere.

---

## `users`

Account record. Email is lower-cased before insert (the API normalises it), so
`UNIQUE(email)` is effectively case-insensitive.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `email` | VARCHAR(255) U NN | login identifier |
| `full_name` | VARCHAR(120) NN | |
| `phone` | VARCHAR(32) | optional, E.164-ish |
| `password_hash` | VARCHAR(255) NN | bcrypt, cost 12 |
| `preferred_language` | VARCHAR(5) NN | `en` \| `ur` |
| `theme` | VARCHAR(10) NN | `light` \| `dark` \| `system` |
| `role` | VARCHAR(20) NN | `farmer` \| `admin` |
| `token_version` | INTEGER NN | bumped on logout-all / password change → invalidates all JWTs |
| `is_active` | BOOLEAN NN | soft deactivation (login refused) |
| `created_at`,`updated_at` | TIMESTAMPTZ NN | |

## `farms`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `user_id` | FK → users, CASCADE | owner |
| `name` | VARCHAR(120) NN | |
| `district` | VARCHAR(80) NN | used for buyer/weather defaults |
| `tehsil` | VARCHAR(80) | |
| `latitude`,`longitude` | NUMERIC(9,6) | required for weather; nullable otherwise |
| `total_area_acres` | NUMERIC(10,2) | informational; crop cycles carry their own area |

## `commodities`

Reference table seeded by `../seed/001_commodities.sql`. `slug` is the stable
identifier shared with the ML pipeline (e.g. `wheat`).

| Column | Type | Notes |
| --- | --- | --- |
| `slug` | VARCHAR(60) U NN | never rename without a data migration |
| `name_en`,`name_ur` | VARCHAR(80) NN | both required — the UI is bilingual |
| `category` | VARCHAR(20) NN | cereal, vegetable, fruit, pulse, cash_crop, other |
| `price_unit` | VARCHAR(20) NN | always `PKR/40kg` today |

## `markets`

Reference table seeded by `../seed/002_markets.sql`. Coordinates are
approximate and only used for proximity ranking.

| Column | Type | Notes |
| --- | --- | --- |
| `slug` | VARCHAR(80) U NN | |
| `district`, `province` | VARCHAR NN | province is CHECK-constrained to the 7 Pakistani units |
| `is_active` | BOOLEAN NN | deactivate rather than delete, to preserve price history |

## `crop_cycles`

The pivot entity: one planting of one commodity, on one farm, in one season.

| Column | Type | Notes |
| --- | --- | --- |
| `farm_id` | FK → farms CASCADE | |
| `commodity_id` | FK → commodities RESTRICT | cannot delete a commodity in use |
| `season` | VARCHAR(10) NN | `rabi` (winter), `kharif` (monsoon), `yearly` |
| `area_acres` | NUMERIC(10,2) NN | CHECK > 0 |
| `sowing_date` | DATE NN | |
| `expected_harvest_date` | DATE | |
| `actual_harvest_date` | DATE | CHECK ≥ sowing_date |
| `status` | VARCHAR(12) NN | planned → active → harvested \| failed |
| `expected_yield_kg`,`actual_yield_kg` | NUMERIC(12,2) | |

## `expenses`

One cost line. `amount_pkr` is a **total amount**, not a rate.

| Column | Type | Notes |
| --- | --- | --- |
| `crop_cycle_id` | FK → crop_cycles CASCADE | |
| `category` | VARCHAR(20) NN | seeds, fertilizer, pesticide, labour, irrigation, transport, machinery, other |
| `amount_pkr` | NUMERIC(12,2) NN | ≥ 0 |
| `expense_date` | DATE NN | |
| `description` | VARCHAR(255) | |

## `sales`

One sale event. `unit_price_pkr` is **PKR per 40 kg**; `total_amount_pkr` is
`quantity_kg / 40 * unit_price_pkr`, stored (and recomputed server-side) so
reporting does not need to re-derive it.

| Column | Type | Notes |
| --- | --- | --- |
| `crop_cycle_id` | FK → crop_cycles CASCADE | |
| `commodity_id` | FK → commodities RESTRICT | denormalised from the cycle for reporting |
| `market_id` | FK → markets SET NULL | delisting a mandi must not delete farmer data |
| `quantity_kg` | NUMERIC(12,2) NN | > 0 |
| `sale_date` | DATE NN | |
| `buyer_name` | VARCHAR(120) | free text, optional |

## `price_records`

Append-only historical quotes. `UNIQUE(commodity_id, market_id, price_date)`
makes ingestion idempotent (re-running an import updates nothing twice).

| Column | Type | Notes |
| --- | --- | --- |
| `price_date` | DATE NN | |
| `min_price_pkr`,`max_price_pkr` | NUMERIC(12,2) | optional range |
| `avg_price_pkr` | NUMERIC(12,2) NN | the value used by models |
| `source` | VARCHAR(30) NN | `amis_punjab`, `pbs`, `synthetic_fixture`, `manual` |

> `synthetic_fixture` rows are generated test data. The API surfaces `source`,
> and the UI must label such series as simulated.

## `forecasts`

One row per issued forecast run, with its evaluation metrics.

| `forecasts` column | Notes |
| --- | --- |
| `model_name` | `seasonal_naive` \| `xgboost` \| `chronos` |
| `horizon_days` | 7 or 30 |
| `issued_on` | date of the last observation used (no leakage) |
| `mae`, `rmse` | hold-out errors in PKR/40kg; NULL if not evaluated |
| `metrics_json` | JSON text (per-step error, training window, params) |

## `forecast_points`

One row per predicted day.

`forecast_points` has `UNIQUE(forecast_id, target_date)` so a re-run replaces
points rather than duplicating them, and optional `lower/upper_bound_pkr` for
models that produce intervals.

## `buyers`

Cache of Google Places results (or manually added buyers).

| Column | Notes |
| --- | --- |
| `place_id` | U NN — Google place id, or `manual:<slug>` for hand-entered buyers |
| `category` | trader, commission_agent, cold_storage, mill, cooperative, other |
| `fetched_at` | drives cache refresh; rows are updated, not deleted |
| `market_id` | optional link to the mandi it serves |

## `weather_snapshots`

Cached weather per farm. `provider` records provenance so the UI can say whether
data came from OpenWeatherMap, Open-Meteo, or a mock (never presented as live).

## `refresh_tokens`

Server-side revocation list. Only the **SHA-256 hash** of the refresh token is
stored; `revoked_at` implements rotation-on-use.

## `reports`

Metadata for generated PDF/Excel files. The bytes live in
`REPORT_STORAGE_DIR` (git-ignored, outside the database). `expires_at` drives a
cleanup job.

---

## Derived values (not stored)

| Value | Derivation | Endpoint |
| --- | --- | --- |
| crop-cycle revenue | `Σ sales.total_amount_pkr` | `/api/v1/crop-cycles/{id}` |
| crop-cycle cost | `Σ expenses.amount_pkr` | same |
| profit / loss | revenue − cost | same |
| break-even price (PKR/40kg) | `cost / (actual_yield_kg / 40)` | `/api/v1/finance/summary` |
| seasonal profit | roll-up across cycles in a season | `/api/v1/finance/summary` |

See [`docs/database/financial-model.md`](../../docs/database/financial-model.md)
for the formulas and rounding rules.
