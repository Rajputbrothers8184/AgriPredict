# Backend scripts

Operational scripts that are run by hand, not imported by the application.

| Script | Purpose | When to run |
| --- | --- | --- |
| `seed_demo_prices.py` | Generate deterministic `synthetic_fixture` price history so the market, forecast and report screens have data | Once, on a fresh demo/dev database |
| `../../scripts/e2e_scenario.py` | Full acceptance walk-through against a live stack | Before a release, or in CI |

## `seed_demo_prices.py`

```bash
cd backend
DATABASE_URL="sqlite:///./agripredict.db" PYTHONPATH=. \
  python scripts/seed_demo_prices.py --days 400
```

It writes ten commodities across six markets (22 800 rows for 400 days) with an
annual price cycle, a Sunday discount, a per-market spread and a seeded random
walk, so the demo looks plausible and cross-market comparison is meaningful.

Three things it deliberately does:

1. **Every row is `source='synthetic_fixture'`.** The API exposes that field and
   the app shows a warning banner for it. Simulated prices must never be
   mistakable for observations.
2. **It refuses to run on a database that contains real prices** unless
   `--force` is given, so fabricated data cannot be quietly mixed into data
   someone collected.
3. **It is deterministic** (`--seed`, default `20261125`), so tests can depend on
   it and two runs produce identical series.

It is idempotent: existing `(commodity, market, date)` rows are skipped, so
re-running extends the series rather than duplicating it.
