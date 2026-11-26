# Installation

Three services and one Android client. Everything below was executed in the
course of building this repository; the verification note at the end of each
section says what was actually observed.

Prerequisites: **Python 3.11** (3.10+ works), **Node 20+**, **JDK 17 + Android
SDK 34** for the client (optional — the API and ML service run without them).

> **Fastest path:** `make setup` once, then `make`. It seeds the database, starts
> both services, health-gates them and stops both on Ctrl-C. The manual steps
> below exist so you can understand and change what it does — they are not an
> alternative you have to follow.

---

## 1. Get the code

```bash
git clone https://github.com/Rajputbrothers8184/AgriPredict.git
cd AgriPredict
cp .env.example .env
```

Then edit `.env` and set a real `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The backend **refuses to start in production** with a known placeholder here, or
with `DEBUG=true`. In development it warns.

---

## 2. Backend API (port 8000)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL="sqlite:///./agripredict.db"
export SECRET_KEY="<the value from .env>"
uvicorn app.main:app --reload --port 8000
```

On first start the app creates the schema and seeds the commodity/market
catalogue from `database/seed/*.sql`. You should see:

```
reference data ready (commodities=16, markets=16)
Uvicorn running on http://127.0.0.1:8000
```

`GET /health` → `{"status":"ok","database":"ok","ml_service":"unavailable"}`
(the ML service is not running yet).

Interactive docs: <http://localhost:8000/docs>.

### Demo price data

A fresh database has **commodities and markets but no prices**, because real
market data cannot be committed (see `docs/ml/`). Seed clearly-labelled
synthetic history:

```bash
cd backend
DATABASE_URL="sqlite:///./agripredict.db" PYTHONPATH=. \
  python scripts/seed_demo_prices.py --days 400
```

```
inserted 22800 synthetic rows (2025-10-22 .. 2026-11-25); 24000 rows in price_records overall
```

Every row carries `source='synthetic_fixture'`. The API exposes that field and
the app shows a warning banner for it. This is the state the screenshots and
the end-to-end scenario assume.

---

## 3. ML service (port 8001)

```bash
cd ml
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt       # CPU-only; no torch
uvicorn inference.service:app --port 8001
```

Check it: `GET http://localhost:8001/health`.

To produce a real forecast you need a fitted model. Train one from the synthetic
fixture (takes under a minute):

```bash
cd ml
python -m training.build_dataset --source datasets/raw/synthetic.csv
python -m training.train_all
```

Trained artefacts land in `ml/saved_models/` and are **not committed** (they are
release assets). Without them, the service answers with the `seasonal_naive`
baseline and says so in the response.

Chronos-T5-Small is an optional ~500 MB download:

```bash
pip install -r requirements-chronos.txt
```

If it is not installed, `/health` reports `chronos.available: false` — which is
the correct, honest state, not an error.

### Verification

With the backend and ML service both up:

```
$ curl -s localhost:8000/health
{"status":"ok","version":"1.0.0","environment":"development","database":"ok","ml_service":"ok"}
```

A forecast made through the backend during the final verification returned
`model: xgboost`, `mae: 103.36`, and a 364.56-wide interval over 7 points.

---

## 4. Android client

```bash
cd frontend
npm install
```

Set the API address **before** building — React Native bakes it in at build
time:

| Where the backend runs | `API_BASE_URL` |
| --- | --- |
| Android emulator | `http://10.0.2.2:8000/api/v1` (default) |
| Physical phone on the same Wi-Fi | `http://<your-LAN-IP>:8000/api/v1` |
| Deployed server | `https://api.example.com/api/v1` |

Create `frontend/.env`:

```bash
cp .env.example .env      # then edit API_BASE_URL
```

`10.0.2.2` is the emulator's alias for the host machine; `localhost` inside the
emulator refers to the emulator itself and will not reach your backend.

Then:

```bash
npm start            # Metro, in one terminal
npm run android      # build + install, in another
```

### Emulator prerequisites

* JDK 17 (`java -version`).
* Android SDK 34 with `ANDROID_HOME` set.
* An AVD, or a device with USB debugging enabled.

### Building a release APK

```bash
cd frontend/android
./gradlew assembleRelease
# → app/build/outputs/apk/release/app-release.apk
```

Signing needs `frontend/android/keystore.properties` (git-ignored). Create it
with four lines:

```properties
storeFile=/absolute/path/to/release.keystore
storePassword=…
keyAlias=agripredict
keyPassword=…
```

A **debug** keystore is committed (`frontend/android/app/debug.keystore`) because
Gradle requires one even to produce a debug build; it is the standard
`android`/`androiddebugkey` pair and signs nothing that should be published.

**This environment cannot build an APK** — there is no Android SDK or device
here. Everything up to the bundle is verified (`npx react-native bundle`
produces a 1,569,037-byte release bundle), but the APK itself has never been
produced by this repository's author in this environment. Treat the Gradle step
as unverified until you run it.

---

## 5. Running everything together

Terminal 1 — ML service:

```bash
cd ml && source .venv/bin/activate && uvicorn inference.service:app --port 8001
```

Terminal 2 — backend:

```bash
cd backend && source .venv/bin/activate
DATABASE_URL="sqlite:///./agripredict.db" ML_SERVICE_ENABLED=true \
ML_SERVICE_URL=http://localhost:8001 WEATHER_PROVIDER=mock \
uvicorn app.main:app --port 8000
```

Terminal 3 — Metro and the app:

```bash
cd frontend && npm start
```

Then, before showing anyone: run the acceptance scenario.

```bash
python scripts/e2e_scenario.py
# 71/71 checks passed in ~1s
```

It registers a throwaway account, builds a farm, a cycle, expenses and sales,
recomputes every financial figure independently, fetches a forecast, downloads a
PDF and an XLSX without an auth header, and checks that a second account cannot
see the first account's data. If that passes, the stack is wired correctly.

---

## 6. Docker / production notes

There are no Dockerfiles in this repository. The two services are plain ASGI
apps and the API is stateless, so the deployment shape is:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4   # behind nginx
```

Before doing that, three things from `docs/security/review.md` matter:

1. **Rate limiting is per process.** With `--workers 4` the effective login
   limit is four times the configured value. Move the buckets to Redis first.
2. **Use PostgreSQL.** SQLite is a single file and does not tolerate multiple
   writers. Set `DATABASE_URL=postgresql+psycopg://…` and run
   `alembic upgrade head`.
3. **Terminate TLS at the proxy** and set `ENVIRONMENT=production`, `DEBUG=false`.
   The app refuses to start with a placeholder secret in production.

`WEATHER_PROVIDER=mock` must not be used in production; without
`OPENWEATHER_API_KEY` it will report `is_live: false` to users, which is honest
but not useful.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ml_service: "unavailable"` in `/health` | ML service not running | Start it on 8001, or accept baseline forecasts |
| Forecast returns `seasonal_naive` | No fitted model | Run `python -m training.train_all` in `ml/` |
| App shows "Network request failed" | `API_BASE_URL` points at the wrong host | Emulator needs `10.0.2.2`, not `localhost` |
| Price screens are empty | No price rows | Run `backend/scripts/seed_demo_prices.py` |
| `429 Too many requests` on login | Rate limiter, 10/minute by default (correct behaviour) | Wait for `retry_after_seconds`, or raise `auth_rate_limit_per_minute` (the setting is in `backend/app/core/config.py`; it is not in `.env.example`) |
| Backend will not start | Placeholder `SECRET_KEY` with `ENVIRONMENT=production` | Generate a real secret |
| `npm audit` shows one high advisory | Metro's build-time `image-size` | Dev-only; see `docs/security/review.md`, finding 2 |
