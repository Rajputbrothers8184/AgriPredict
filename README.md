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

Requires Git, Node.js 20+, Python 3.11+. Full details in
[`docs/installation/`](docs/installation/).

```bash
git clone https://github.com/Rajputbrothers8184/AgriPredict.git
cd AgriPredict
cp .env.example .env          # then set SECRET_KEY

# Backend API  → http://localhost:8000/docs
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# ML service   → http://localhost:8001/docs   (second terminal)
cd ml
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn inference.service:app --reload --port 8001

# Android app  (third terminal)
cd frontend
npm install
npm run android
```

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

Interactive API docs: <http://localhost:8000/docs>. Contract reference:
[`docs/api/`](docs/api/).

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
python -m pipeline.build_dataset          # ingest + preprocess
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

```bash
cd backend && pytest -q                 # unit + API tests
cd ml       && pytest -q                # preprocessing + forecast-shape tests
cd frontend && npm test                 # jest component/unit tests
pytest tests/                           # cross-module integration tests
```

CI runs the same commands (see `.github/workflows/`). Model training is **never**
run in CI.

## 16. Building and deploying

**Android release APK**

```bash
cd frontend/android
./gradlew assembleRelease      # → app/build/outputs/apk/release/app-release.apk
```

Requires a signing keystore (`frontend/android/keystore.properties`, git-ignored).
Full steps: [`docs/installation/android-build.md`](docs/installation/).

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

Assignments are **tentative** until the team confirms them. Own contribution
record: [`docs/team-contributions.md`](docs/team-contributions.md).

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
