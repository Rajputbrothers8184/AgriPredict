# Entity–Relationship Diagram

Rendered by GitHub from the Mermaid block below. Keys: **PK** primary key,
**FK** foreign key, **U** unique, **NN** not null.

```mermaid
erDiagram
    USERS ||--o{ FARMS : owns
    USERS ||--o{ REFRESH_TOKENS : holds
    USERS ||--o{ REPORTS : requests
    FARMS ||--o{ CROP_CYCLES : has
    FARMS ||--o{ WEATHER_SNAPSHOTS : records
    COMMODITIES ||--o{ CROP_CYCLES : planted_as
    COMMODITIES ||--o{ PRICE_RECORDS : priced_in
    COMMODITIES ||--o{ FORECASTS : forecast_for
    COMMODITIES ||--o{ SALES : sold_as
    MARKETS ||--o{ PRICE_RECORDS : quoted_at
    MARKETS ||--o{ SALES : sold_at
    MARKETS ||--o{ FORECASTS : forecast_at
    MARKETS ||--o{ BUYERS : hosts
    CROP_CYCLES ||--o{ EXPENSES : incurs
    CROP_CYCLES ||--o{ SALES : yields
    FORECASTS ||--|{ FORECAST_POINTS : contains

    USERS {
        int id PK
        varchar email U "NN, lower-cased"
        varchar full_name
        varchar phone
        varchar password_hash "NN, bcrypt"
        varchar preferred_language "en|ur"
        varchar theme "light|dark|system"
        varchar role "farmer|admin"
        int token_version "invalidates issued tokens"
        bool is_active
        timestamptz created_at
        timestamptz updated_at
    }

    FARMS {
        int id PK
        int user_id FK "-> USERS, ON DELETE CASCADE"
        varchar name "NN"
        varchar district "NN"
        varchar tehsil
        numeric latitude "nullable, -90..90"
        numeric longitude "nullable, -180..180"
        numeric total_area_acres
        timestamptz created_at
        timestamptz updated_at
    }

    COMMODITIES {
        int id PK
        varchar slug U "NN, e.g. wheat"
        varchar name_en "NN"
        varchar name_ur "NN"
        varchar category "cereal|vegetable|fruit|pulse|cash_crop|other"
        varchar price_unit "PKR/40kg"
        timestamptz created_at
    }

    MARKETS {
        int id PK
        varchar slug U "NN"
        varchar name "NN"
        varchar district "NN"
        varchar province "NN"
        numeric latitude
        numeric longitude
        bool is_active
        timestamptz created_at
    }

    CROP_CYCLES {
        int id PK
        int farm_id FK "-> FARMS, ON DELETE CASCADE"
        int commodity_id FK "-> COMMODITIES, RESTRICT"
        varchar season "rabi|kharif|yearly"
        numeric area_acres "NN, > 0"
        date sowing_date "NN"
        date expected_harvest_date
        date actual_harvest_date
        varchar status "planned|active|harvested|failed"
        numeric expected_yield_kg
        numeric actual_yield_kg
        text notes
        timestamptz created_at
        timestamptz updated_at
    }

    EXPENSES {
        int id PK
        int crop_cycle_id FK "-> CROP_CYCLES, CASCADE"
        varchar category "seeds|fertilizer|pesticide|labour|irrigation|transport|machinery|other"
        numeric amount_pkr "NN, >= 0"
        date expense_date "NN"
        varchar description
        timestamptz created_at
    }

    SALES {
        int id PK
        int crop_cycle_id FK "-> CROP_CYCLES, CASCADE"
        int commodity_id FK "-> COMMODITIES, RESTRICT"
        int market_id FK "-> MARKETS, SET NULL"
        numeric quantity_kg "NN, > 0"
        numeric unit_price_pkr "NN, PKR per 40 kg"
        numeric total_amount_pkr "NN, derived and stored"
        date sale_date "NN"
        varchar buyer_name
        timestamptz created_at
    }

    PRICE_RECORDS {
        int id PK
        int commodity_id FK "-> COMMODITIES, CASCADE"
        int market_id FK "-> MARKETS, CASCADE"
        date price_date "NN"
        numeric min_price_pkr "per 40 kg"
        numeric max_price_pkr "per 40 kg"
        numeric avg_price_pkr "NN, per 40 kg"
        varchar source "amis_punjab|pbs|synthetic_fixture"
        timestamptz created_at
    }

    FORECASTS {
        int id PK
        int commodity_id FK "-> COMMODITIES, CASCADE"
        int market_id FK "-> MARKETS, CASCADE"
        varchar model_name "seasonal_naive|xgboost|chronos"
        int horizon_days "7 or 30"
        date issued_on "NN, data cutoff date"
        numeric mae
        numeric rmse
        json metrics_json "extra evaluation detail"
        timestamptz created_at
    }

    FORECAST_POINTS {
        int id PK
        int forecast_id FK "-> FORECASTS, CASCADE"
        date target_date "NN"
        numeric predicted_price_pkr "NN"
        numeric lower_bound_pkr
        numeric upper_bound_pkr
    }

    BUYERS {
        int id PK
        varchar place_id U "NN, Google place id or local slug"
        varchar name "NN"
        varchar category "trader|commission_agent|cold_storage|mill|cooperative|other"
        varchar address
        varchar district
        numeric latitude
        numeric longitude
        numeric rating
        int user_ratings_total
        varchar phone
        int market_id FK "-> MARKETS, SET NULL"
        timestamptz fetched_at "cache freshness"
    }

    WEATHER_SNAPSHOTS {
        int id PK
        int farm_id FK "-> FARMS, CASCADE"
        timestamptz observed_at
        numeric temperature_c
        numeric humidity_pct
        numeric wind_kph
        numeric precipitation_mm
        varchar condition
        varchar provider "openweathermap|open-meteo|mock"
        json raw_json
        timestamptz created_at
    }

    REFRESH_TOKENS {
        int id PK
        int user_id FK "-> USERS, CASCADE"
        varchar token_hash U "NN, sha256"
        timestamptz expires_at
        timestamptz revoked_at
        timestamptz created_at
    }

    REPORTS {
        int id PK
        int user_id FK "-> USERS, CASCADE"
        varchar report_type "financial_summary|crop_cycle|forecast"
        varchar file_format "pdf|xlsx"
        varchar filename
        int size_bytes
        timestamptz created_at
        timestamptz expires_at
    }
```

## Relationship rules

| Rule | Reason |
| --- | --- |
| `farms → users` cascades | deleting a user removes their farm data (GDPR-style erasure); the API requires explicit confirmation |
| `crop_cycles → farms` cascades | a cycle cannot exist without a farm |
| `expenses`, `sales → crop_cycles` cascade | they have no meaning without the cycle |
| `commodities` use `RESTRICT` | never silently orphan historical prices or sales |
| `sales.market_id` uses `SET NULL` | a delisted mandi must not delete a farmer's sale record |
| `price_records` unique on `(commodity_id, market_id, price_date)` | one quote per commodity/market/day — makes ingestion idempotent |
| `forecast_points` unique on `(forecast_id, target_date)` | one value per day per forecast |
| `buyers.place_id` unique | Google place ids are stable; enables UPSERT caching |
| `refresh_tokens.token_hash` unique | one live row per issued token |

## Indexes

Chosen for the actual query patterns (chart ranges, dashboards, ingestion):

| Index | Serves |
| --- | --- |
| `idx_price_records_commodity_date` | historical chart: filter commodity, order by date |
| `idx_price_records_market_date` | market comparison |
| `idx_expenses_cycle_date` | per-cycle ledger, ordered by date |
| `idx_sales_cycle_date` | revenue rollup |
| `idx_crop_cycles_farm_status` | "my active crops" dashboard |
| `idx_forecasts_lookup` | newest forecast for (commodity, market, horizon) |
| `idx_buyers_district` | nearby-buyer fallback when the Places API is unavailable |
| `idx_weather_farm_observed` | latest weather per farm |

## Notes and deliberate omissions

- **No separate `financial_records` table.** The specification mentions it, but
  profit/loss is fully derivable from `expenses` and `sales`. Storing a third
  copy would create a consistency problem. `GET /api/v1/finance/summary` derives
  it instead — see `docs/database/financial-model.md`.
- **No multi-tenant table.** One deployment serves one cooperative/family;
  ownership is per `user_id`.
- **Price history is append-only.** Corrections are new rows with a later
  `created_at`, so charts remain reproducible.
