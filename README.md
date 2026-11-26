# AgriPredict

**Crop Price Forecasting and Farm ERP**

An Android application (React Native) with a separate Python machine-learning
prediction service that helps farmers manage crops and finances, follow market
prices, forecast future prices, check weather, compare markets, and discover
nearby agricultural buyers.

> **Project status:** under active development — see
> [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md) for the live, honest
> status of every module (what works, what is stubbed, what is blocked).

---

## Table of contents

1. [Overview](#1-overview)
2. [Problem statement](#2-problem-statement)
3. [Objectives](#3-objectives)
4. [Key features](#4-key-features)
5. [System architecture](#5-system-architecture)
6. [Technology stack](#6-technology-stack)
7. [Repository structure](#7-repository-structure)
8. [Quick start](#8-quick-start)
9. [Frontend setup](#9-frontend-setup)
10. [Backend setup](#10-backend-setup)
11. [Database setup](#11-database-setup)
12. [Machine-learning setup](#12-machine-learning-setup)
13. [External API configuration](#13-external-api-configuration)
14. [Running the complete system](#14-running-the-complete-system)
15. [Testing](#15-testing)
16. [Building and deploying](#16-building-and-deploying)
17. [Team roles](#17-team-roles)
18. [Contributing](#18-contributing)
19. [Limitations](#19-limitations)
20. [Licence](#20-licence)

---

## 1. Overview

Smallholder farmers in Pakistan routinely sell below the best available market
price because price information is scattered, delayed, or simply unavailable in
a usable form. AgriPredict puts four things in one Android app:

| Capability | What the farmer gets |
| --- | --- |
| **Farm ERP** | Crop cycles, expenses, sales and a profit/loss ledger per season |
| **Price forecasting** | 7-day and 30-day price outlook per commodity/market, with a stated accuracy measure |
| **Market & weather context** | Historical prices, mandi comparison, current conditions and short forecast |
| **Buyer discovery** | Nearby traders, commission agents and cold-storage facilities |

The app is bilingual (**English / اردو**) with **light and dark** themes, and
exports financial and forecast records to **PDF** and **Excel**.

## 2. Problem statement

1. **Information asymmetry** — farmers depend on intermediaries for prices and
   often learn the market rate after the sale.
2. **No forward visibility** — price direction over the next days/weeks is
   unknown, so harvesting and selling decisions are made blind.
3. **No farm records** — costs and revenues are not tracked, so profitability
   per crop cycle cannot be established.
4. **Fragmented tools** — weather, market rates, and buyer contacts live in
   different places (or nowhere), and existing agri apps are English-only and
   urban-oriented.

## 3. Objectives

1. Provide one offline-tolerant Android application covering farm records,
   finances, market information, weather and buyers.
2. Deliver a reproducible, honest forecasting service that reports MAE/RMSE
   instead of promising accuracy, and 7-day / 30-day horizons.
3. Remain usable on low-end Android hardware and on intermittent connectivity.
4. Support Urdu so the target user is not excluded by language.
5. Keep every module independently ownable by a four-person team, with a clean
   Git history and reproducible setup.

## 4. Key features

**Authentication** — registration, login, JWT access + refresh tokens, secure
on-device token storage.

**Farm ERP** — crop cycles (crop, area, sowing/harvest dates, status), expense
tracking with categories, sales records, per-cycle profit/loss summary.

**Market intelligence** — commodity and market (mandi) catalogue, historical
price charts, cross-market comparison, forecast with model metadata.

**Forecasting** — three models behind one interface: Seasonal Naive (baseline),
XGBoost (feature-based), Amazon Chronos-T5-Small (zero-shot foundation model).
The API always returns which model produced a forecast and its measured error.

**Weather** — current conditions plus short forecast for the farm's location.

**Buyer discovery** — nearby buyers via Google Maps Platform Places, with
cached results so the feature still shows something useful offline.

**Reports** — PDF (human-readable statement) and Excel (multi-sheet workbook).

**Localisation & theming** — full English/Urdu string catalogue with RTL
support; light/dark/system themes.

## 5. System architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Android device                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ React Native app (frontend/)                           │  │
│  │  screens → hooks/context → services (axios)            │  │
│  │  SQLite cache (offline reads) · i18n · theming         │  │
│  └───────────────┬────────────────────────────────────────┘  │
└──────────────────┼───────────────────────────────────────────┘
                   │ HTTPS / JSON (JWT bearer)
┌──────────────────▼───────────────────────────────────────────┐
│  Backend API — FastAPI (backend/)                            │
│   api/ routes · services/ business logic · schemas/ contracts│
│   auth · crops · expenses · sales · finance · markets        │
│   weather · buyers · forecasts · reports                     │
└──┬────────────┬───────────────┬────────────────┬─────────────┘
   │ SQLAlchemy │ HTTP          │ HTTP           │ HTTP
┌──▼─────────┐ ┌▼─────────────┐ ┌▼─────────────┐ ┌▼─────────────┐
│ PostgreSQL │ │ ML service   │ │ Weather API  │ │ Places API   │
│ or SQLite  │ │ (ml/)        │ │ OpenWeather  │ │ Google Maps  │
│ (database/)│ │ FastAPI +    │ │ /Open-Meteo  │ │ Platform     │
│            │ │ Chronos,     │ └──────────────┘ └──────────────┘
│            │ │ XGBoost,     │
│            │ │ SeasonalNaive│
└────────────┘ └──────────────┘
```

**Design decisions worth knowing**

- The ML service is a **separate process** (`ml/`, port 8001) so that training
  dependencies (PyTorch, Chronos) never touch the API container or the app.
- The backend **degrades instead of failing**: with no ML service it falls back
  to its own statistical baseline; with no weather key to Open-Meteo; with no
  Places key the buyer endpoint returns a documented `503`.
- The Android app **never** talks to Google or the ML service directly — every
  third-party key stays server-side.
- Full rationale: [`docs/architecture/`](docs/architecture/).

## 6. Technology stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Mobile | React Native 0.8x, JavaScript/JSX, React Navigation | Android only |
| Mobile state/storage | React Context, AsyncStorage, MMKV-style cache via SQLite | offline-first reads |
| Charts | `react-native-svg` + custom chart components | no paid SDK |
| Reports | backend-generated PDF (ReportLab) and Excel (OpenPyXL) | app only downloads |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic v2 | async-capable |
| ORM / DB | SQLAlchemy 2.x, Alembic; SQLite (dev) / PostgreSQL (shared) | see `database/` |
| Auth | OAuth2 password flow, JWT (access + refresh), bcrypt (passlib) | |
| ML | Python 3.11, pandas, NumPy, scikit-learn, XGBoost, PyTorch, Chronos | CPU-feasible |
| Weather | OpenWeatherMap (primary), Open-Meteo (keyless fallback) | free tiers |
| Buyers | Google Maps Platform Places API | billing required |
| CI | GitHub Actions (lint, tests, schema checks) | no model training in CI |

All of the above are free/open-source except the two external APIs, which have
free tiers; see §13.

## 7. Repository structure

```
AgriPredict/
├── frontend/          React Native application (Role 1)
│   ├── src/{components,screens,navigation,services,hooks,context,
│   │        assets,localization,utils}
│   ├── android/       native Android project (generated)
│   └── tests/
├── backend/           FastAPI service (Role 2)
│   ├── app/{api,core,services,schemas,middleware,utils}
│   └── tests/
├── ml/                Forecasting service + research code (Role 3)
│   ├── datasets/{raw,processed,fixtures}
│   ├── preprocessing/  models/  training/  evaluation/  inference/
│   ├── saved_models/   (weights published via Releases, not committed)
│   └── tests/
├── database/          Schema, migrations, seed data, ER diagram (Role 4)
│   ├── schema/  migrations/  seed/  diagrams/
├── docs/              architecture, api, database, ml, installation,
│                      testing, user-guide
├── tests/             cross-module integration & system tests
├── .github/           workflows, issue and PR templates
├── .env.example       configuration template (real .env is ignored)
├── CONTRIBUTING.md    team workflow rules
├── DEVELOPMENT_PROGRESS.md  live status board
└── README.md
```

Each module has its own `README.md` describing that department's contract.

## 8. Quick start

Requires Git, Python 3.11+ and GNU Make. Node 20+ is only needed for the Android
client. Full details in [`docs/installation/`](docs/installation/).

### One command

```bash
git clone https://github.com/Rajputbrothers8184/AgriPredict.git
cd AgriPredict
make setup      # once: creates .venv, installs backend + ML + frontend deps
make            # every time: starts everything
```

`make` does the whole local bring-up:

1. finds a Python interpreter that has the dependencies,
2. creates the SQLite schema and seeds reference data (16 commodities, 16 markets),
3. seeds 24,000 labelled demo price rows and a demo account if the database is new,
4. starts the ML service on 8001 and the API on 8000,
5. **health-gates both** — the API's `/health` polls the ML service, so this fails
   loudly instead of printing a URL that will error on the first request,
6. streams both logs with `[API]` / `[ML]` prefixes and stops both on Ctrl-C.

```
  Ready
    API      http://127.0.0.1:8000
    docs     http://127.0.0.1:8000/docs
    health   http://127.0.0.1:8000/health
    ML       http://127.0.0.1:8001/docs

  Demo account (seeded):  demo@agripredict.pk / Sunflower2026
```

Useful flags and variants:

```bash
make api                          # API only; forecasts fall back to the baseline
python scripts/dev.py --reload    # auto-restart on code changes
make seed                         # re-run the demo price seeder explicitly
make test                # all four offline suites (~1 min)
make test-e2e            # 71 acceptance checks against the running stack
make help                # every target
```

`scripts/dev.py` is a plain Python wrapper around the same documented commands —
it is not a second source of truth. Confirm what it will run with
`python scripts/dev.py --help`.

### Without Make

`scripts/dev.py` is the whole thing — `make` only calls it:

```bash
python3 scripts/dev.py            # same bring-up, same flags
python3 scripts/dev.py --help     # every option
python3 scripts/dev.py --no-ml    # API only
```

### Windows

`scripts/dev.py` works, but the `make` targets assume a POSIX shell. Use WSL, or
run the two `uvicorn` commands from
[`docs/installation/README.md`](docs/installation/README.md) in separate terminals.

### Embedding the API in a browser preview

The API sends `X-Frame-Options: DENY` by default, which blocks iframes. A hosted
preview that renders the API in a frame needs:

```bash
python scripts/dev.py --frame-options SAMEORIGIN
# or set FRAME_OPTIONS=SAMEORIGIN FRAME_ANCESTORS="https://*.example.app"
```

Relaxed framing is refused at startup when `ENVIRONMENT=production`.

### Android client

The API and ML service run without it; the client needs the Android SDK:

```bash
cd frontend
npm install
echo "API_BASE_URL=http://10.0.2.2:8000/api/v1" > .env   # 10.0.2.2 = host, from an emulator
npm run android
```

**No APK is built or verified in this repository** — there is no Android SDK in
its development environment. See [`docs/installation/`](docs/installation/).

## 9. Frontend setup

```bash
cd frontend
npm install
npm start            # Metro bundler
npm run android      # build + install on emulator/device
```

Prerequisites: JDK 17, Android Studio with SDK 34, an emulator or a device with
USB debugging enabled. The API base URL is configured in
`frontend/.env` (copied from `frontend/.env.example`); `10.0.2.2` is the
emulator's alias for the host machine.

See [`frontend/README.md`](frontend/README.md).

## 10. Backend setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # create/refresh the schema
uvicorn app.main:app --reload
```

Interactive OpenAPI docs: <http://localhost:8000/docs>. The frontend's view of
the contract is frozen in `frontend/tests/fixtures/apiContract.json` and checked
by `scripts/regen_api_contract.py` (see
[`docs/frontend/api-contract.md`](docs/frontend/api-contract.md)).

## 11. Database setup

SQLite needs nothing. For PostgreSQL:

```bash
createdb agripredict
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/agripredict
cd backend && alembic upgrade head
```

Schema, ER diagram and seed data: [`database/`](database/).

## 12. Machine-learning setup

```bash
cd ml
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt           # CPU-only extras by default
python -m training.build_dataset --source datasets/raw/synthetic.csv
python -m training.train_all              # fit/compare models, write metrics
uvicorn inference.service:app --port 8001
```

**Read [`docs/ml/`](docs/ml/) before training.** Chronos-T5-Small is ~500 MB of
weights; the default `requirements.txt` installs CPU-only PyTorch. Trained
artefacts are published as GitHub Release assets, not committed.

## 13. External API configuration

| Service | Key variable | Free tier | Behaviour without a key |
| --- | --- | --- | --- |
| OpenWeatherMap | `OPENWEATHER_API_KEY` | yes (60 calls/min) | falls back to Open-Meteo |
| Open-Meteo | — | yes, no key | used as fallback |
| Google Places | `GOOGLE_PLACES_API_KEY` | monthly credit, **billing required** | endpoint returns `503` with explanation |

Put keys in `.env` (git-ignored). Never commit them, never share them in chat.

## 14. Running the complete system

1. Start the ML service (port 8001).
2. Start the backend (port 8000) — it discovers the ML service via
   `ML_SERVICE_URL`.
3. Start Metro and install the Android app.
4. Register a user in the app; the backend seeds the commodity/market catalogue
   on first start.

Health checks: `GET /health` on both services.

## 15. Testing

Four suites, all runnable offline:

```bash
cd database && pytest tests -q          # 45   schema, parity, constraints
cd backend  && pytest -q                # 161  unit, API and 36 security tests
cd ml       && pytest tests -q          # 85   preprocessing, models, service
cd frontend && npx jest                 # 179  components, services, i18n
```

Two further layers need a running stack:

```bash
python scripts/e2e_scenario.py          # 71   end-to-end acceptance over HTTP
python scripts/load_smoke.py            # latency + concurrency consistency
```

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs the four suites, the
linter, both dependency audits, the API-contract check and a Metro bundle build
on every push. It does **not** build an APK (no Android SDK in CI), and model
training is never run in CI — see [Testing](#15-testing).

Coverage: backend 87%, database 94%, ML source 84%, frontend 70% of lines.
Details, including what is deliberately uncovered:
[`docs/security/review.md`](docs/security/review.md).

## 16. Building and deploying

**Android release APK**

```bash
cd frontend/android
./gradlew assembleRelease      # → app/build/outputs/apk/release/app-release.apk
```

Requires a signing keystore (`frontend/android/keystore.properties`, git-ignored).
**No APK has been built in this project's environment** — there is no Android SDK
or emulator here — so treat the Gradle step as unverified. What *is* verified is
that the JavaScript bundle compiles for release (1,569,037 bytes). Full steps,
including the emulator/LAN address table:
[`docs/installation/`](docs/installation/).

**Services** — the backend and ML service are plain ASGI apps; either run
`uvicorn` behind a reverse proxy or build the provided images. Hosting the ML
service publicly is optional: on-device/baseline forecasts work without it.

## 17. Team roles

Four members, generic labels only (no personal data is stored in this repo).

| Role | Ownership | Folder | Branch |
| --- | --- | --- | --- |
| Member 1 — Frontend | React Native UI, navigation, i18n, theming, exports UI | `frontend/` | `feature/frontend` |
| Member 2 — Backend | FastAPI, auth, business logic, integrations | `backend/` | `feature/backend` |
| Member 3 — ML | datasets, preprocessing, Chronos/XGBoost/baselines, evaluation | `ml/` | `feature/ml-model` |
| Member 4 — Database | schema, ERD, migrations, seed, integrity tests | `database/` | `feature/database` |

Assignments are **tentative** until the team confirms them. No personal data is
stored in this repository; the module-by-module record of what exists and what is
verified is [`DEVELOPMENT_PROGRESS.md`](DEVELOPMENT_PROGRESS.md).

## 18. Contributing

Branch strategy, commit conventions and review rules are in
[`CONTRIBUTING.md`](CONTRIBUTING.md). Short version: branch from `develop`,
use Conventional Commits, open a PR, never push unfinished work to `main`.

## 19. Limitations

Honest, current limitations — these are not marketing caveats:

1. **Historical price data is not bundled.** The repository ships a real
   ingestion pipeline plus a small, clearly-labelled synthetic fixture used
   only for pipeline tests. Forecast accuracy figures measured on that fixture
   validate the *pipeline*, not real market behaviour. Real accuracy requires
   the official AMIS Punjab / PBS series (see `docs/ml/datasets.md`).
2. **Android builds are not produced in CI** — no emulator or SDK is available
   in the CI/dev sandbox, so APKs must be built locally and attached to a
   release manually.
3. **Weather and buyer features need API keys**; without them the app shows a
   documented degraded state rather than invented data.
4. **Chronos** is implemented as an optional adapter. It requires PyTorch and a
   ~500 MB weight download; if unavailable the service reports the fallback
   model it actually used.
5. **Android-only.** No iOS target is built or tested.
6. **Single-tenant deployment assumed.** No multi-farm tenancy, no offline
   write-conflict resolution beyond last-write-wins.

## 20. Licence

MIT — see [`LICENSE`](LICENSE).
