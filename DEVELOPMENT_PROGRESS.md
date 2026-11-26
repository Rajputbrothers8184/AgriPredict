# Development Progress

Live status board. Update this file **after every completed milestone**, with
honest states — `done`, `in progress`, `blocked`, `not started`. A phase is only
`done` when its verification step has actually been run.

Last updated: 2026-11-26

---

## Phase board

| # | Phase | Status | Verified how |
| --- | --- | --- | --- |
| 1 | Project initialization (structure, governance docs, git) | **done** | `21d820d`, tree reviewed, pushed |
| 2 | Database first (ERD, schema, migrations, seed, tests) | **done** | `b2a483b`; 45 database tests pass |
| 3 | Backend development (FastAPI, auth, APIs, tests) | **done** | `8298483`; 125 API tests pass |
| 4 | Machine learning (data, preprocessing, 3 models, evaluation) | **done** | `28a8a68`; 85 ML tests pass; live service drove real forecasts |
| 5 | Frontend (React Native screens, i18n, theming, exports) | **done with limitations** | 160 Jest tests, Metro release bundle, 11 live API tests. **No APK** — no Android SDK here |
| 6 | Integration (frontend ↔ backend ↔ ML, external APIs) | **done with limitations** | `scripts/e2e_scenario.py`: 71/71 checks over real HTTP incl. backend→ML forecast and PDF/XLSX download; external APIs (weather/Places/Chronos) unavailable and reported honestly |
| 7 | Final testing (unit, API, DB, ML, integration, security) | **done with limitations** | 36 backend + 13 frontend security tests; 48 dependency advisories cleared; 2 findings fixed, 3 accepted and documented; coverage 87/94/84/70%; load smoke 196 req/s with no lost updates (`docs/security/review.md`) |
| 8 | Release (docs, artifacts, tag `v1.0.0`) | **done with limitations** | Docs set (architecture, installation, user guide, security, ML, contract, testing); `CHANGELOG.md`; CI workflow; versions unified at 1.0.0. **No APK and no git tag** — no Android SDK here, and tagging is the owner's call |

### Test totals

| Layer | Tests | Command |
| --- | --- | --- |
| Database | 45 | `cd database && pytest tests -q` |
| ML service | 85 | `cd ml && pytest tests -q` |
| Backend (incl. 39 security) | **167** | `cd backend && pytest -q` |
| Frontend (incl. 13 security) | **173** | `cd frontend && npx jest` |
| Frontend live integration (opt-in) | 11 | `LIVE_API=1 npx jest tests/live.integration.test.js` |
| **End-to-end acceptance** | **71 checks** | `python scripts/e2e_scenario.py` (needs a running stack) |
| **Total** | **470 automated** + 11 live + 71 e2e + load smoke | |

## Environment / capability matrix

Measured in the development sandbox on 2026-11-25:

| Capability | Available | Consequence |
| --- | --- | --- |
| GitHub (gh CLI, ADMIN on repo) | ✅ | commits + pushes verifiable |
| Python 3.11 + PyPI | ✅ | backend + ML importable and testable |
| Node 22 + npm registry | ✅ | 160 frontend tests; Metro release bundle compiles |
| JDK / Android SDK / emulator | ❌ | **no APK, no device/emulator run**; native project comes from the official RN template and is unbuilt |
| OpenWeatherMap / Open-Meteo | ❌ (blocked) | weather integration code + tests only, mocks |
| Google Places API | ❌ (blocked) | buyers code + tests only, mocks |
| Hugging Face (Chronos weights) | ❌ (blocked) | adapter tested via a stub pipeline; real-weight path unverified; no Chronos accuracy is reported |
| AMIS Punjab / PBS datasets | ❌ (blocked) | real accuracy impossible; synthetic fixture used |

## Modules

| Module | Owner role | Status | Notes |
| --- | --- | --- | --- |
| Repository skeleton + governance | Backend (lead) | done | |
| Database schema & migrations | Member 4 | done | 16 tables, ERD, seed, integrity tests |
| Backend auth | Member 2 | done | JWT access/refresh, rotation, token versioning |
| Backend crops / expenses / sales / finance | Member 2 | done | server-derived totals and finance block |
| Backend markets / weather / buyers / forecasts / reports | Member 2 | done | reports now also serve signed download links |
| ML data pipeline | Member 3 | done | strict validation incl. series-median unit checks |
| ML models (SeasonalNaive, XGBoost, Chronos) | Member 3 | done with limitation | Chronos adapter written and stub-tested; real weights never loaded |
| ML inference service | Member 3 | done | FastAPI on :8001, 503 on unavailable model |
| Frontend shell, navigation, theming, i18n | Member 1 | done | 5 tabs + shared stack, light/dark, en/ur with RTL |
| Frontend feature screens | Member 1 | done | 19 screens incl. dashboard, crops, market, forecast, finance, weather, buyers, reports, settings |
| Integration tests | All | in progress | frontend↔backend live suite (11) done; cross-service scenario tests remaining |
| Android release build | Member 1 | **blocked** | no SDK here; Gradle project is committed and must be built locally |

## Branches

| Branch | Purpose | State |
| --- | --- | --- |
| `main` | stable releases | exists |
| `develop` | integration | created from `main` |
| `feature/frontend` | Member 1 | created from `develop` |
| `feature/backend` | Member 2 | created from `develop` |
| `feature/ml-model` | Member 3 | created from `develop` |
| `feature/database` | Member 4 | created from `develop` |
| `arena/77981720-agripredict` | agent working branch for this session | active |

> Note: the Arena session branch is where the development agent commits. Team
> members work on their `feature/*` branches and merge into `develop` via PRs.

## Known issues / decisions to confirm

1. **Repository visibility** — the GitHub repo is currently **public**; the
   specification prefers private. Changing visibility requires the owner's
   approval, so it has **not** been changed.
2. **Role assignments** — the mapping in §17 of the README is the default from
   the specification and is **tentative** until the team confirms it.
3. **Real crop-price dataset** — unavailable from the sandbox. Pipeline is
   written for the documented AMIS/PBS format; a synthetic fixture drives tests.
   Metrics must not be presented as real-market accuracy.
4. **Android build** — cannot be produced here. The native project is the
   standard RN 0.76 template with AgriPredict's manifest, label and ProGuard
   rules; it must be built on a machine with Android Studio. Everything that
   could be verified without an SDK was: 160 tests and a release Hermes bundle.
5. **Report downloads needed a backend change.** The download endpoint required
   an `Authorization` header, which a browser or Android download manager cannot
   send. Added short-lived signed `?token=` links (single-report scope, capped at
   the report's own expiry); bearer auth still works for API clients. Covered by
   8 new backend tests including tampering, wrong-report and expiry cases.
6. **Frontend/backend contract drift was found and fixed before release.**
   The screens were first written against assumed field names (`amount`,
   `price_per_maund`, `predictions`) instead of the real schemas (`amount_pkr`,
   `unit_price_pkr`, `points`). Because the app renders "—" for a missing field,
   nothing failed visibly. A generated contract test
   (`frontend/tests/apiContract.test.js`, 31 assertions against the FastAPI
   OpenAPI schema) now fails if a field the app reads disappears.
7. **New architecture disabled** in `frontend/android/gradle.properties`. Reason
   and re-enable path are documented in `frontend/README.md`.
8. **Sign-out does not instantly invalidate the access token.** `POST /auth/logout`
   revokes only the refresh token, so a stolen access token keeps working for up
   to 60 minutes. `logout-all` and `change-password` do invalidate immediately
   (they bump `token_version`). This is the standard stateless-JWT trade-off; the
   options and their cost are laid out in `docs/testing/e2e-scenario.md`. Left as
   a documented decision for the owner rather than changed unilaterally.
9. **The demo database needed price data.** Only one market had quotes, which
   made the cross-market comparison screen useless. Added
   `backend/scripts/seed_demo_prices.py`, which generates deterministic
   `synthetic_fixture` rows for 10 commodities × 6 markets, refuses to mix them
   into a database holding real prices, and is labelled in the UI.

## Next approved task

All eight phases are complete. What remains is not a phase but a short list of
things that need a capability this environment does not have, or a decision only
the project owner can make:

1. **Build and run the APK** on a real device (needs the Android SDK and a
   phone). Everything up to the release bundle is verified; Gradle is not.
2. **Load real price data** (AMIS Punjab / PBS) under a licence that permits
   redistribution. Until then every forecast is a demonstration of the method.
3. **Decide on logout revocation** — `docs/security/review.md`, finding 4.
4. **Move rate limiting to Redis** before any multi-worker deployment.
5. **Tag `v1.0.0` and attach release assets** once an APK exists. Tagging is
   deliberately left to the owner; nothing here is pushed as a release.
