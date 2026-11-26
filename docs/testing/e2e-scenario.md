# End-to-end acceptance scenario

`scripts/e2e_scenario.py` walks the entire product the way a real client does —
over HTTP, against a running stack, with nothing mocked and nothing in-process.

```bash
python scripts/e2e_scenario.py                     # defaults to http://127.0.0.1:8000/api/v1
python scripts/e2e_scenario.py --require-ml        # fail if the forecast is a fallback
python scripts/e2e_scenario.py --base-url https://api.example.com
```

Exit code `0` means every check passed; the last line reports the count
(currently **71 checks in ~20 s**).

## What it walks

| # | Section | Representative assertions |
| --- | --- | --- |
| 1 | Health | `/health` reachable, database `ok`, `ml_service` reported |
| 2 | Authentication | unauthenticated and bogus-token requests are `401` |
| 3 | Registration | new account isolated (zero farms); both token types issued |
| 4 | Reference data | commodities and markets seeded; both language names present |
| 5 | Farm | create succeeds; one coordinate without the other is `422` |
| 6 | Crop cycle | create succeeds; harvest-before-sowing is `422` |
| 7 | Expenses | four categories stored exactly; category filter; negative amount refused |
| 8 | Sales | **server derives the total** (400 kg @ 4000/maund → 40 000) |
| 9 | Finance | revenue, cost, profit, margin, break-even and yield-per-acre all recomputed and compared; overview agrees with the cycle; expense mix sums to cost |
| 10 | Market | history fields and unit; comparison spans six markets; a best market is named |
| 11 | Forecast | 7 points, ordered non-degenerate interval containing the prediction, real model + measured MAE, disclaimer present |
| 12 | Reports | PDF (`%PDF`) and XLSX (`PK`) fetched **with no auth header**, forged token refused |
| 13 | Integrations | weather states its provider and whether it is live; buyers report their source; both degrade honestly |
| 14 | Isolation | a second account cannot read or delete the first account's cycle (`404`, not `403`) |
| 15 | Token lifecycle | refresh rotates; a spent refresh token is rejected; `logout-all` invalidates the access token |

## Why assertions target derived values

Echoing input back proves only that JSON deserialises. Every check that matters
here recomputes an independent value and compares:

* 400 kg at PKR 4 000/maund must be **40 000**, not whatever the client sent —
  this is the 1 maund = 40 kg conversion that a units bug breaks.
* Break-even must be **cost ÷ harvested maunds** = 30 000 ÷ 15 = **2 000**.
* A forecast interval must be **ordered and non-degenerate** — a zero-width band
  shipped once during development and looked perfectly plausible on screen.
* A PDF must begin with `%PDF` and be more than 1 000 bytes, because an HTML
  error page served with `200` would otherwise pass.

## Data it creates

Each run registers throwaway users at `@agripredict-e2e.pk` and builds one farm,
one cycle, four expenses, two sales and two reports. Nothing is deleted
afterwards; the demo database accumulates `e2e.*` accounts.

Because the API rate-limits registration, the client honours the API's own
`retry_after_seconds` (up to three times) instead of failing. A scenario that
cannot be run twice in a row is useless in CI.

## Known limitation it documents

`POST /auth/logout` revokes the **refresh** token only. The already-issued access
token stays valid until it expires (60 minutes by default). This is the standard
stateless-JWT trade-off, and the scenario asserts it explicitly rather than
pretending otherwise:

```
[PASS] logout revokes the refresh token
[PASS] access token remains valid until expiry after logout (known JWT trade-off)
[PASS] logout-all invalidates the access token immediately
```

`POST /auth/logout-all` (and `change-password`) bump `token_version`, which
invalidates every access token immediately. If a deployment needs instant
revocation on ordinary sign-out, the cheapest correct change is to bump
`token_version` there too — at the cost of signing the user out on all devices.
That decision is left to the project owner; it is recorded here so it is a
known choice rather than an overlooked bug.

## Prerequisites

```bash
# backend, from backend/
DATABASE_URL="sqlite:///./agripredict.db" \
ML_SERVICE_ENABLED=true ML_SERVICE_URL=http://localhost:8001 \
WEATHER_PROVIDER=mock SECRET_KEY="demo-secret-key-long-enough-1234567890" \
PYTHONPATH=. uvicorn app.main:app --port 8000

# ML service, from ml/ (optional; without it the forecast check reports a fallback)
uvicorn inference.service:app --port 8001

# price data, from backend/ (only needed for a fresh database)
DATABASE_URL="sqlite:///./agripredict.db" PYTHONPATH=. \
  python scripts/seed_demo_prices.py --days 400
```

The scenario is not part of `pytest` (it needs a live server) and is not part of
`npm test` (it is language-agnostic). Run it before a release, and in CI once a
stack is available.
