# Frontend — React Native (Android)

Mobile client for AgriPredict: crop-cycle record keeping, market prices, a
short-term price forecast, and PDF/Excel statements.

> **Scope of verification.** Everything below was exercised in this build
> environment: 160 Jest tests, a release Hermes bundle compiled with Metro, and
> 11 live integration tests against the running FastAPI backend. **The Gradle
> native build was never executed** — no Android SDK/NDK is installed here — so
> an APK has not been produced. See [Not verified](#not-verified).

---

## Quick start

```bash
cd frontend
npm install                 # ~350 MB of node_modules
cp .env.example .env        # set API_BASE_URL for your machine
npm start                   # Metro bundler
npm run android             # build + install on an emulator or device
```

`API_BASE_URL` must be reachable **from the phone**, not from your laptop:

| Where the app runs | Value |
| --- | --- |
| Android emulator | `http://10.0.2.2:8000/api/v1` (`10.0.2.2` is the host machine) |
| Physical device on the same Wi-Fi | `http://<your-LAN-IP>:8000/api/v1` |
| Production | `https://your-domain.example/api/v1` |

React Native bakes this in at build time, so changing it requires a rebuild
(a Metro reload is not enough for a release APK).

## Scripts

| Command | Purpose |
| --- | --- |
| `npm test` | 160 unit/component tests (hermetic, ~4 s) |
| `npm run test:coverage` | Same, with coverage |
| `npm run lint` | ESLint (`@react-native` config) |
| `npm run format` | Prettier |
| `npm start` | Metro bundler |
| `npm run android` | Debug build onto a device |
| `npm run android:release` | Release APK (`android/app/build/outputs/apk/release/`) |
| `npm run android:bundle` | Release AAB for Play Store |

Live integration tests are opt-in and need a running backend:

```bash
LIVE_API=1 API_BASE_URL=http://127.0.0.1:8000/api/v1 \
  DEMO_EMAIL=demo@agripredict.pk DEMO_PASSWORD=Sunflower2026 \
  npx jest tests/live.integration.test.js
```

They exercise the real `src/services/api.js` wrappers — the only way to catch a
path or field-name mismatch that mocked unit tests cannot see.

## Structure

```
frontend/
├── index.js                     AppRegistry entry
├── android/                     Native shell (standard RN 0.76 template)
├── src/
│   ├── App.js                   Provider composition + StatusBar
│   ├── config.js                API base URL, storage keys, price unit
│   ├── navigation/
│   │   └── RootNavigator.js     Auth stack vs. tab stack, theme wiring
│   ├── screens/
│   │   ├── auth/                Welcome, Login, Register
│   │   ├── crops/               List, Form, Detail, ExpenseForm, SaleForm
│   │   ├── market/              Market prices, Forecast
│   │   ├── DashboardScreen.js
│   │   ├── FinanceScreen.js     Lifetime rollups + season + expense mix
│   │   ├── FarmFormScreen.js
│   │   ├── WeatherScreen.js
│   │   ├── BuyersScreen.js
│   │   ├── ReportsScreen.js
│   │   ├── SettingsScreen.js
│   │   └── MoreScreen.js
│   ├── components/
│   │   ├── ui.js                Text, Card, Button, Input, Badge, states…
│   │   └── PriceChart.js        react-native-svg line chart + forecast band
│   ├── context/
│   │   ├── AuthContext.js       Session lifecycle, login/logout
│   │   ├── ThemeContext.js      light / dark / system, persisted
│   │   └── LocalizationContext.js  en / ur + RTL
│   ├── services/
│   │   ├── apiClient.js         fetch wrapper: timeout, errors, 401 refresh
│   │   ├── api.js               One function per backend route
│   │   └── session.js           Token storage + single-flight refresh
│   ├── hooks/useAsync.js        loading / error / data with stale-response guard
│   ├── localization/            en.js, ur.js, lookup + interpolation
│   ├── theme/palette.js         Contrast-checked colours, spacing, typography
│   ├── constants/options.js     Enums mirrored from the backend schemas
│   └── utils/                   format, validation, finance, errors
└── tests/                       12 suites, 160 tests
```

## Design decisions worth knowing

**Money never appears without its unit.** Prices are per 40 kg (maund) and a
missing unit is the most likely source of a factor-of-40 error, so
`formatPriceWithUnit` is the default and a bare `formatPrice` is used only where
the column header states the unit.

**Number formatting is hand-written, not `Intl`.** ICU builds disagree on
rendering the `PKR` currency code (`PKR` vs `Rs`), and Hermes ships only partial
`Intl` support on Android. `utils/format.js` implements 3-digit grouping, which
matches Pakistani bank statements and PBS tables (not the 2,2,3 lakh grouping).

**The server owns the arithmetic.** `FinanceOverview` and `CropCycleDetail.finance`
are displayed as-is, so the app and the exported PDF/XLSX statement can never
disagree. `utils/finance.js` only fills gaps where the server has no value yet
(optimistic preview, offline) and is pinned to `finance_service` semantics by
tests — including 1 maund = 40 kg.

**One refresh in flight.** Refresh tokens rotate, so three expired requests
firing `POST /auth/refresh` concurrently would log the user out twice over.
`session.refreshSession()` collapses them into one promise.

**Honest surfaces.** A forecast built by the fallback model shows a badge; a
synthetic price series shows a warning banner; mock weather says it is simulated;
an unconfigured buyer search explains itself instead of showing an empty list.
Reaching a farmer with a number that looks authoritative but is not is the
failure mode this app cares most about avoiding.

**Report downloads use signed links.** `download_url` carries a short-lived
`?token=` so Android's download manager — which sends no headers — can fetch the
file. The app never hands a long-lived access token to the system browser.

## Testing

| Suite | What it covers |
| --- | --- |
| `apiClient.test.js` | URL building, bearer auth, error envelope, 401 → single refresh, timeout/offline |
| `session.test.js` | Persistence, corrupt storage, refresh rotation, concurrency, sign-out |
| `apiContract.test.js` | **Every field the app reads exists in the backend OpenAPI schema**, and every field it writes is accepted |
| `screens.test.js`, `screens2.test.js` | Login validation, dashboard, market, forecast, crops CRUD, expenses, sales, weather, buyers, reports, farm form |
| `finance.test.js` | Maund conversion, profit/margin, break-even, breakdown normalisation |
| `format.test.js`, `validation.test.js`, `i18n.test.js`, `errors.test.js`, `hooks.test.js`, `components.test.js` | Pure logic, catalogue parity, chart rendering |

The contract test is generated from the backend, so a field rename fails here
with the exact schema name instead of silently rendering "—" in production:

```bash
python scripts/regen_api_contract.py   # from the repository root
```

Details and the rules that keep it useful: [`docs/frontend/api-contract.md`](../docs/frontend/api-contract.md).

## Localisation

English and Urdu catalogues must stay key-for-key; `i18n.test.js` fails if a key
is missing from either file, if a translation is empty, or if a `{placeholder}`
differs between the two.

Urdu layout is right-to-left. React Native cannot flip direction at runtime
without a reload, so switching language writes the preference and applies full
RTL on the next launch; the Settings screen says so explicitly.

## Build configuration

* **New architecture disabled** (`newArchEnabled=false`). The app adds no custom
  native modules, and a Fabric mismatch with the third-party native libraries is
  a build failure, not a runtime warning. Re-enabling is a one-line change once
  those libraries are pinned to a consistent Fabric-compatible set.
* **ABIs**: all four for debug; narrow this for release to cut the APK size.
* **ProGuard/R8** rules in `android/app/proguard-rules.pro` keep the native
  module entry points that stripping would break only at runtime.
* `usesCleartextTraffic` is **not** enabled in the manifest. Pointing
  `API_BASE_URL` at a plain `http://` LAN address works in a debug build only if
  you add a network-security-config exemption for that host; production must be
  HTTPS.

## Not verified

| Item | Status |
| --- | --- |
| Gradle build / APK produced | ❌ no Android SDK in this environment |
| App launched on a device or emulator | ❌ same reason |
| RTL layout visually inspected in Urdu | ❌ logic tested; visual check needs a device |
| Push notifications | ❌ not implemented |
| Offline write queue | ❌ reads fail soft; write actions require connectivity |
| iOS | ❌ Android only, per project scope |
| Google Places buyer search | ❌ returns `source: "unavailable"` without an API key |
| Weather from a real provider | ❌ `WEATHER_PROVIDER=mock` in this environment; the mock is labelled in the UI |
