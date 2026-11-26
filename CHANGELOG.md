# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Version `1.0.0` is the first release that is internally consistent end to end:
every number in the app comes from the API, every claim in the documentation is
either executed or labelled unverified, and the limitations are enumerated
rather than implied.

---

## [1.0.0] — 2026-11-25

### Added

**Database**
- Canonical schema (16 tables) with an ERD, Alembic migrations and seed data for
  16 commodities and 16 markets.
- 45 tests covering schema parity between SQL and the ORM, check constraints,
  unique constraints and referential integrity.
- Documented financial model: every derived figure and its formula
  (`docs/database/financial-model.md`).

**Backend API**
- FastAPI service with JWT authentication (bcrypt, rotation, typed claims,
  token-version revocation), farms, crop cycles, expenses, sales, derived
  finance, market history and comparison, weather, buyer search and reports.
- Server-derived financials: revenue, cost, profit, margin, break-even and
  yield-per-acre are computed from rows and never accepted from a client.
- PDF (reportlab) and XLSX (openpyxl) report generation with short-lived signed
  download links, so a browser or Android download manager can fetch a file
  without an `Authorization` header.
- One JSON error envelope for every failure mode, with no traceback leakage.
- 161 tests, including 36 security tests.

**Machine learning**
- Preprocessing, feature engineering and three models: seasonal naive, XGBoost,
  and an optional Chronos adapter.
- Backtesting and MAE/RMSE reporting; the API response always names the model
  that produced the forecast and its measured error.
- Non-degenerate prediction intervals derived from measured residual spread.
- 85 tests.

**Android app (React Native 0.76)**
- 19 screens: auth, dashboard, farms, crop cycles, expenses, sales, finance,
  market prices, forecast chart, weather, buyers, reports, settings.
- Bilingual English/Urdu with RTL layout, light/dark/system themes.
- No-Redux state design, refresh de-duplication, offline-tolerant reads with
  AsyncStorage caching, and a hand-rolled number formatter that does not depend
  on Hermes' `Intl` coverage.
- 179 tests, including 13 security tests and 6 sign-out behaviour tests.

**Verification and operations**
- `scripts/e2e_scenario.py` — 71-check acceptance walk-through over real HTTP.
- `scripts/load_smoke.py` — latency percentiles plus a concurrency consistency
  check that fails on a lost update.
- `scripts/regen_api_contract.py` — regenerates the frontend's frozen API fixture
  and fails if a schema disappears.
- `backend/scripts/seed_demo_prices.py` — deterministic, clearly-labelled
  synthetic price history across 10 commodities × 6 markets.
- `.github/workflows/ci.yml` — four suites, lint, both dependency audits, the
  contract check and a Metro release bundle build.
- Documentation set: architecture, installation, user guide, security review,
  ML evaluation, API contract and testing.

### Changed

- **Dependencies upgraded to clear 48 known vulnerabilities.** `fastapi 0.165.0`,
  `starlette 1.10.0`, `pyjwt 2.15.1`, `python-multipart 0.0.34`,
  `pydantic 2.14.4`, `pydantic-settings 2.14.2`, `sqlalchemy 2.0.44`,
  `uvicorn 0.38.0`. `pip-audit` now reports none.
- `@react-native/metro-config` and the RN CLI moved from `dependencies` to
  `devDependencies`. They are build-time tools and never ship in an APK.
- Version is defined once per layer (`backend/app/__init__.py`,
  `frontend/src/config.js`) instead of being duplicated as a literal.
- Demo price data now spans six markets per commodity. It previously covered one
  market, which made cross-market comparison — a headline feature — return a
  single row.

### Fixed

- **The API could not be embedded in a browser preview.** `X-Frame-Options: DENY`
  was sent unconditionally, so any iframe-rendered preview showed a blank frame.
  The policy is now configurable (`FRAME_OPTIONS`, `FRAME_ANCESTORS`) with the
  secure default unchanged, a matching `frame-ancestors` CSP, and a production
  boot check that refuses anything but `DENY`.
- **A wildcard in `CORS_ORIGINS` silently failed every preflight.** Starlette
  matches `allow_origins` as literal strings, so `https://*.example.com` never
  matched and the preflight returned 400 with no `allow-origin` header. Added
  `CORS_ORIGIN_REGEX` for patterns and tests for the exact-origin, regex and
  refused-origin paths.

- **URL scheme not validated before handing it to the OS.** The report download
  URL accepted any `http`-prefixed string, and externally-sourced buyer phone
  numbers were interpolated straight into `tel:`. Both now go through
  `safeExternalUrl()` / `telUri()`.
- `logout` used a dynamic `import()` for a module already imported at the top of
  the file, which broke under Jest's CommonJS transform.
- Naive datetimes from SQLite were compared against timezone-aware values in
  report expiry checks.
- The frontend API fixture had drifted from the backend schema; it is now
  generated and CI fails if it drifts again.
- "Sign out on all devices" existed in the API but not in the app. It is now in
  the More screen, behind a confirmation, and wired to the endpoint that bumps
  `token_version`.

### Known limitations

Deliberate, documented and unchanged by this release:

1. **No APK has been built.** No Android SDK or emulator exists in this project's
   environment. The release JavaScript bundle compiles (1,569,037 bytes); the
   Gradle step is unverified.
2. **Price history is `synthetic_fixture`.** Real AMIS Punjab / PBS series are not
   redistributable. Every published MAE validates the pipeline, not market
   behaviour. The API exposes `source` and the app warns.
3. **Chronos weights are not shipped.** `/health` reports
   `chronos.available: false`; XGBoost and the naive baseline are what run.
4. **Weather is `mock`** and **buyer search is unconfigured** in this
   environment. Both report that fact instead of inventing data.
5. **Ordinary sign-out does not revoke the access token**, only the refresh
   token. `logout-all` and `change-password` do. See
   `docs/security/review.md`, finding 4.
6. **Rate limiting is per process.** A multi-worker deployment multiplies the
   effective limit; Redis is required before scaling out.
7. **Android only.** There is no iOS target.

### Not verified in this environment

Stated explicitly because a release note that omits this is misleading:

- No APK was assembled, installed or run on a device or emulator.
- RTL layout was tested structurally (text direction, mirrored styles) but not
  visually on a device.
- No live weather or Google Places key was available, so both integrations were
  exercised only in their degraded paths.
- No penetration test was performed; the security review is code-level plus
  automated tests.
- Load figures are from a single-process dev server on SQLite and are not a
  capacity claim.
