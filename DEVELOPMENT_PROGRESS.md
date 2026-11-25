# Development Progress

Live status board. Update this file **after every completed milestone**, with
honest states — `done`, `in progress`, `blocked`, `not started`. A phase is only
`done` when its verification step has actually been run.

Last updated: 2026-11-25

---

## Phase board

| # | Phase | Status | Verified how |
| --- | --- | --- | --- |
| 1 | Project initialization (structure, governance docs, git) | **in progress** | files reviewed, committed, pushed |
| 2 | Database first (ERD, schema, migrations, seed, tests) | not started | — |
| 3 | Backend development (FastAPI, auth, APIs, tests) | not started | — |
| 4 | Machine learning (data, preprocessing, 3 models, evaluation) | not started | — |
| 5 | Frontend (React Native screens, i18n, theming, exports) | not started | — |
| 6 | Integration (frontend ↔ backend ↔ ML, external APIs) | not started | — |
| 7 | Final testing (unit, API, DB, ML, integration, security) | not started | — |
| 8 | Release (docs, artifacts, tag `v1.0.0`) | not started | — |

## Environment / capability matrix

Measured in the development sandbox on 2026-11-25:

| Capability | Available | Consequence |
| --- | --- | --- |
| GitHub (gh CLI, ADMIN on repo) | ✅ | commits + pushes verifiable |
| Python 3.11 + PyPI | ✅ | backend + ML importable and testable |
| Node 22 + npm registry | ✅ | frontend JS/testable |
| JDK / Android SDK / emulator | ❌ | **no APK build, no device test** |
| OpenWeatherMap / Open-Meteo | ❌ (blocked) | weather integration code + tests only, mocks |
| Google Places API | ❌ (blocked) | buyers code + tests only, mocks |
| Hugging Face (Chronos weights) | ❌ (blocked) | Chronos adapter untestable; fallbacks tested |
| AMIS Punjab / PBS datasets | ❌ (blocked) | real accuracy impossible; synthetic fixture used |

## Modules

| Module | Owner role | Status | Notes |
| --- | --- | --- | --- |
| Repository skeleton + governance | Backend (lead) | in progress | this commit set |
| Database schema & migrations | Member 4 | not started | |
| Backend auth | Member 2 | not started | |
| Backend crops / expenses / sales / finance | Member 2 | not started | |
| Backend markets / weather / buyers / forecasts / reports | Member 2 | not started | |
| ML data pipeline | Member 3 | not started | |
| ML models (SeasonalNaive, XGBoost, Chronos) | Member 3 | not started | |
| ML inference service | Member 3 | not started | |
| Frontend shell, navigation, theming, i18n | Member 1 | not started | |
| Frontend feature screens | Member 1 | not started | |
| Integration tests | All | not started | |
| Android release build | Member 1 | blocked | no SDK in sandbox; build locally |

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
4. **Android build** — cannot be produced here. Instructions are complete; the
   build must be executed on a machine with Android Studio.

## Next approved task

Phase 2 — database schema, ERD, migrations, seed data and integrity tests
(Member 4), then Phase 3 backend on top of it.
