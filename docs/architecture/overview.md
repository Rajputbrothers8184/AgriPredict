# Architecture overview

How AgriPredict is put together, and — more usefully — **why** it is put
together that way. Every decision below was made under a specific constraint;
the constraint is stated with the decision, because the constraint is what a
future maintainer needs in order to know when the decision stops applying.

---

## 1. Shape of the system

```
┌─────────────────────┐   HTTPS/JSON   ┌──────────────────────┐   HTTP   ┌──────────────────┐
│  Android app        │ ─────────────► │  Backend API         │ ───────► │  ML service      │
│  React Native 0.76  │ ◄───────────── │  FastAPI + SQLAlchemy│ ◄─────── │  FastAPI (models)│
│  (screens, i18n)    │                │  auth, ERP, reports  │          │  XGBoost/naive   │
└─────────────────────┘                └──────────┬───────────┘          └──────────────────┘
        │                                         │
        │ AsyncStorage (tokens, cache)            │ SQLAlchemy 2.0
        │                                         ▼
        │                              ┌──────────────────────┐
        │                              │  PostgreSQL / SQLite │
        │                              └──────────────────────┘
        │            browser / download manager
        └──────────────────────────────►  /reports/{id}/download?token=…   (signed, 5 min)
```

Three deployables, one database. The app never talks to the ML service or the
database directly; the backend is the only trusted client of both.

### Why three deployables rather than one

The ML service holds model weights and a heavy numerical stack (pandas, numpy,
XGBoost, optionally torch). The backend is a thin API that must start in under a
second and stay cheap to run. Putting them in one process would force the API's
cold-start and memory profile to follow the ML stack's.

The cost of the split is honest and visible: the ML service can be down, and the
backend then has to answer anyway. That path is not an afterthought — the
backend falls back to a documented baseline and **reports which model actually
produced the number** (`docs/ml/evaluation.md`). A forecast response always
carries `model`, `mae` and a `disclaimer`, so a degraded answer cannot be
mistaken for a good one.

---

## 2. Backend

```
backend/app/
├── main.py              app assembly: routers, middleware, error envelope
├── core/
│   ├── config.py        pydantic-settings; refuses to start insecurely
│   ├── security.py      bcrypt, JWT issue/verify, signed download tokens
│   ├── exceptions.py    AppError hierarchy → one JSON error shape
│   └── logging_config.py
├── api/
│   ├── deps.py          DbSession, CurrentUser, rate limiting
│   ├── routes_auth.py   register/login/refresh/logout/me/change-password
│   ├── routes_farms.py  farms and crop cycles
│   ├── routes_finance.py expenses, sales, derived summary
│   ├── routes_markets.py commodities, markets, price history, comparison
│   ├── routes_forecasts.py  forecast retrieval + ML delegation
│   ├── routes_reports.py    PDF/XLSX generation and signed downloads
│   ├── routes_weather.py
│   └── routes_buyers.py
├── services/            business logic; routes stay thin
├── schemas/             pydantic models, strict on input
└── models.py            SQLAlchemy ORM
```

**Layering rule:** a route validates, authorises and delegates. Money and units
arithmetic lives in `services/` (not in routes, not in the client) because it is
the part that must be identical for every caller — the API, the PDF, the Excel
export and the mobile screen all show the same numbers only if one place
computes them.

### The finance model is server-side on purpose

The API computes `revenue`, `cost`, `profit`, `margin`, `break-even` and
`yield-per-acre` from rows, and returns them as a derived block. It does **not**
accept a total from the client. Two concrete reasons:

1. **Units.** A sale is recorded in kilograms; the market quotes in **maunds
   (40 kg)**. If the client sent `total_amount_pkr`, a client bug in the kg→maund
   conversion would silently write a 40×-wrong revenue into the ledger. The
   backend derives it from `quantity_kg × price_per_maund / 40` instead, and the
   reconciliation is covered by a test and by the end-to-end scenario.
2. **Consistency.** The same figure appears in the API response, the PDF and the
   spreadsheet. Deriving it once guarantees they cannot disagree.

The trade-off: the client cannot record a total that disagrees with its own line
items, which is correct for this product but would be wrong for an accounting
system that needs to preserve a negotiated amount.

### Error envelope

Every failure — validation, authentication, domain, unexpected — is rendered as:

```json
{"error": {"code": "insufficient_stock", "message": "...", "details": {"..."}}}
```

One shape means the mobile client has one error path (`src/utils/errors.js`)
rather than a different branch per endpoint, and it means a stack trace can
never reach a user: the handler logs the traceback with the request id and
returns the envelope. `docs/security/review.md` asserts that no error body
contains a traceback, a class name or a filesystem path.

---

## 3. Database

Schema, ERD and integrity tests live in `database/` and are the single source of
truth; the ORM mirrors them, and a parity test fails if the two drift.

Three decisions that shape the rest:

* **Money is `NUMERIC(12, 2)`, never float.** Binary floating point cannot
  represent 0.10 and a ledger that is off by a paisa per row is not a ledger.
* **Every child row carries a `user_id` reachable by join, and every query
  filters on it.** Row-level isolation is enforced in the query, not by trusting
  a path parameter. A missing `user_id` filter would be a cross-tenant read, so
  the security tests assert that another user's resource is a **404, not a 403**
  — not confirming existence matters as much as not returning the data.
* **Derived values are not stored.** Profit, margin and break-even are computed
  from expenses and sales on read. Storing them would create a second source of
  truth that a deleted expense could contradict.

The price table is `(commodity_id, market_id, price_date)` unique, with the
`source` column constrained to a known set. That constraint is what makes the
synthetic-data labelling enforceable rather than a convention: the demo seed
writes `synthetic_fixture`, the API exposes it, and the app shows a warning
banner for it.

---

## 4. Machine learning

```
ml/
├── datasets/        raw + processed (raw is not redistributable; see docs/ml)
├── preprocessing/   loaders, feature engineering (deterministic, tested)
├── models/          seasonal_naive, xgboost, chronos adapter
├── evaluation/      metrics, backtesting
├── training/        build_dataset.py, train_all.py  (CLIs, not imported at runtime)
└── inference/       service.py (FastAPI), registry.py (artefact loading)
```

**Why three models.** A forecast that cannot be beaten by a naive baseline is
not worth shipping. `seasonal_naive` (same day last week) is therefore a real
competitor, evaluated on identical splits, and the reported MAE always states
which model produced it. XGBoost won on the fixture data.

**Interval, not a point.** Every point carries a lower and upper bound derived
from measured residual spread. The frontend test suite asserts the interval is
ordered and **not degenerate** — a zero-width band shipped once during
development and looked completely plausible on screen.

**What the numbers mean.** The published MAE is measured on a
`synthetic_fixture` series, so it validates the pipeline, not Pakistani market
behaviour. This is stated in `docs/ml/evaluation.md`, in the API response, and
in the app's forecast screen. It is not a caveat buried in a README.

---

## 5. Frontend

```
frontend/src/
├── config.js            build-time values with local fallbacks
├── services/
│   ├── apiClient.js     fetch wrapper: auth, timeout, one retry, error mapping
│   ├── api.js           typed endpoint functions (one per backend route)
│   └── session.js       token storage, refresh de-duplication
├── contexts/            auth, language/theme
├── screens/             19 screens
├── components/          ui.js primitives, PriceChart (react-native-svg)
├── localization/        en.js, ur.js, index.js  (no hardcoded strings)
└── utils/               finance, format, validation, errors
```

Decisions with reasons:

* **No Redux.** The app's shared state is a session and a language/theme choice.
  A store would add a dependency and a mental model without removing a problem.
  Screen data is fetched per screen and cached in AsyncStorage where a stale read
  is better than a spinner.
* **A hand-rolled number formatter, not `Intl`.** `Intl.NumberFormat` renders
  `"Rs 3,900"` on some ICU builds and may not exist at all on Hermes for the
  currency path. A formatter that throws on a price render is not shippable, so
  grouping is implemented in `utils/format.js` and unit-tested.
* **Units are part of the label.** Prices are always rendered with `PKR/40kg`
  attached. A price without its unit is the most likely source of a factor-of-40
  misunderstanding between a farmer and a trader.
* **Refresh de-duplication.** Refresh tokens rotate, so three screens firing
  requests with an expired access token would each try to refresh; only the first
  would succeed and the other two would be signed out. `session.js` collapses
  concurrent refreshes into one promise.
* **Scheme validation before handing a URL to the OS.** Anything passed to
  `Linking.openURL` leaves the app's sandbox, so `safeExternalUrl()` allowlists
  `https/http/tel/mailto` and `telUri()` strips dialler metacharacters from
  externally-sourced phone numbers (see `docs/security/review.md`, finding 3).

---

## 6. Reports

PDF (reportlab) and Excel (openpyxl) are generated **server-side**. Generating
them on the device would mean shipping a PDF and a spreadsheet engine inside the
APK, and would make the exported numbers depend on the client's build.

Downloads have two authentication paths because there are two kinds of caller:
an API client that can send `Authorization`, and a browser or Android download
manager that cannot. The latter uses a short-lived signed token in the URL
(`/reports/{id}/download?token=…`, 5-minute TTL), bound to both the user and the
report id. Credentials presented in the header take precedence over the link, so
a second user's session cannot borrow someone else's URL.

---

## 7. External integrations

| Integration | Failure behaviour | Why |
| --- | --- | --- |
| Weather | Falls back to a mock provider that reports `is_live: false` | A weather card that silently shows invented values is worse than one that says it is simulated |
| Buyer search (Google Places) | Returns `source: "unavailable"` with an empty list | Requires billing; the honest empty state is the correct one |
| ML service | Falls back to a baseline and reports the model actually used | The app stays useful; the response never claims more than it did |
| Chronos weights | Adapter is optional; service reports `chronos.available: false` | ~500 MB of weights are not redistributable in this repository |

The pattern is deliberate: **degrade, but say so**. Every one of those
degradations is surfaced in the response and rendered in the UI, and the
end-to-end scenario asserts that the response includes the flag rather than
looking successful.

---

## 8. What is not here, and why

| Absent | Reason | What it would take |
| --- | --- | --- |
| Multi-tenant / multi-farm sharing | Single-farmer product; would need a membership table and a permission model | Design work, not a patch |
| Offline write queue | Reads are cached; writes fail honestly when offline | Conflict resolution (last-write-wins would lose data) |
| Push notifications | No FCM project configured | Credentials + a backend sender |
| iOS build | No macOS host; never compiled | A Mac and an iOS pass |
| Horizontal scaling | Rate limits are in-process, SQLite is a single file | Redis + PostgreSQL + a stateless API tier |
| Real market data | AMIS Punjab / PBS series are not redistributable | A licensed data agreement |
