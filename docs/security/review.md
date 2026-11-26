# Security review

Scope: the AgriPredict monorepo — FastAPI backend, PostgreSQL/SQLite schema, ML
service and the React Native client. Review date 2026-11-25.

This document records what was **tested**, what was **found**, what was
**fixed**, and what is **accepted risk**. Automated coverage lives in
`backend/tests/test_security.py` (36 tests) and `frontend/tests/security.test.js`
(13 tests). Anything not backed by a test or a scan is marked as such.

---

## 1. Summary

| Area | Result |
| --- | --- |
| Authentication | Pass — bcrypt, JWT with typed claims, rotation, revocation |
| Authorisation | Pass — every protected route rejects anonymous access; cross-user access returns 404 |
| Injection | Pass — parameterised ORM use throughout; hostile strings stored as data |
| Dependency vulnerabilities | **Fixed** — 48 advisories cleared in the backend, prod frontend deps reduced to one build-time advisory |
| Secrets in the repository | Pass — none present; placeholders rejected in production |
| Transport / headers | Pass with caveats — headers set, TLS left to the deployment |
| Client-side data handling | **Fixed** — URL scheme gate added; see finding 3 |
| Rate limiting | Pass with a documented limitation — in-process only |

Two findings were fixed during the review, one is accepted with a recorded
decision. All other categories passed with no change.

---

## 2. Findings

### Finding 1 — 48 known vulnerabilities in pinned backend dependencies (High) — FIXED

`pip-audit -r backend/requirements.txt` reported:

```
Found 48 known vulnerabilities in 3 packages
python-multipart 0.0.20  (6 advisories, fix 0.0.34)
pyjwt            2.10.1  (22 advisories, fix 2.15.1)
starlette        0.41.3  (20 advisories, fix 1.10.0)
```

PyJWT matters most: this is the library that verifies every access token.

**Fix.** Upgraded the web stack: `fastapi 0.165.0`, `starlette 1.10.0`,
`pyjwt 2.15.1`, `python-multipart 0.0.34`, `pydantic 2.14.4`,
`pydantic-settings 2.14.2`, `sqlalchemy 2.0.44`, `uvicorn 0.38.0`.

Starlette crossed a major version (0.41 → 1.10) and FastAPI crossed 0.115 → 0.165,
so the upgrade was verified rather than assumed: **all 125 backend tests pass**,
the 36 new security tests pass, the 71-check end-to-end scenario passes, and the
load smoke test passes against the upgraded server.

```
$ pip-audit -r requirements.txt
No known vulnerabilities found
```

### Finding 2 — one high-severity advisory in an unused frontend package (Medium) — MITIGATED

`npm audit --omit=dev` reported `image-size` (infinite loop parsing hostile
JXL/HEIF/ICNS headers), reached transitively through
`@react-native/metro-config → metro → image-size`.

That chain is **build-time only** — Metro runs on a developer machine, not on a
phone — but it sat in `dependencies`, which is why the production audit flagged
it. `npm audit fix` cannot resolve it without `--force` (a breaking downgrade of
meteor's own dependency tree).

**Fix.** `@react-native/metro-config` and the `@react-native-community/cli`
packages were moved from `dependencies` to `devDependencies`. Runtime
dependencies are now the nine libraries the app actually ships: React Native,
React, the three navigation packages, safe-area-context, screens, svg and
async-storage. The affected package is still present, is still dev-only, and the
remaining advisory is documented rather than suppressed.

### Finding 3 — API-controlled URLs were opened without validating their scheme (Medium) — FIXED

Two places handed a value from a server response straight to the operating
system:

* `absoluteDownloadUrl()` returned any string starting with `http`, and
  `ReportsScreen` passed the result to `Linking.openURL`. A response containing
  `javascript:`, `data:` or `file:` would have been dispatched to another app.
  The API is trusted today, but a report URL is exactly the kind of value that
  ends up user- or vendor-influenced.
* `BuyersScreen` interpolated a buyer's phone number — from an **external**
  Places provider, not our own database — directly into `tel:${phone}`. A value
  with dialler metacharacters (`#`, `;`, `*`) could append parameters.

**Fix.** `src/utils/format.js` now exposes `safeExternalUrl()` (allowlist:
`https`, `http`, `tel`, `mailto`) and `telUri()` (strips everything except
digits, `+`, `-`, spaces and parentheses; rejects fewer than five digits). Both
call sites use them, and 13 frontend tests assert the hostile cases are refused.
Covered by `frontend/tests/security.test.js`.

### Finding 4 — sign-out does not revoke the access token (Low) — ACCEPTED, documented

`POST /auth/logout` revokes the refresh token. An access token already issued
stays valid until it expires (60 minutes by default).

This is the standard stateless-JWT trade-off and is **not** changed
unilaterally: making logout revoke access tokens means either a database lookup
on every request or signing the user out on all devices. `POST /auth/logout-all`
and `change-password` already invalidate immediately by bumping
`token_version`, so the capability exists.

Recorded in `docs/testing/e2e-scenario.md`; the scenario asserts the actual
behaviour instead of pretending otherwise. The decision belongs to the project
owner.

### Finding 5 — rate limiting is per process (Low) — ACCEPTED, documented

Login and registration are throttled with a fixed window held in process
memory. This stops credential stuffing against a single-process deployment, but
a multi-worker or multi-instance deployment multiplies the effective limit by
the worker count. Moving the buckets to Redis is the correct fix and is recorded
as a deployment requirement, not a code change to make now.

### Finding 6 — tokens in AsyncStorage (Low) — ACCEPTED, documented

Access and refresh tokens are stored with `@react-native-async-storage`, which
is not encrypted at rest. On a rooted device or a device with a compromised
backup they are readable. `android:allowBackup="false"` is already set, which
closes the backup path. Encrypted storage (`react-native-keychain`/`Keystore`)
is the mitigation and requires a native dependency that cannot be built and
tested in this environment — adding it untested would be worse than the current
honest state.

---

## 3. What passed, and the evidence

### Authentication

* Passwords are bcrypt hashed (`$2b$`, work factor 12) and never stored or
  returned in plaintext. Two users with the same password get different hashes.
* Tokens carry a `type` claim and are rejected in the wrong role: a refresh
  token cannot be used as an access token, and a report-download token cannot
  be used as an access token.
* Tokens signed with a different secret, `alg: none` tokens, and expired tokens
  are all rejected.
* Login failure is indistinguishable for an unknown email and a wrong password —
  same status, same message — so email enumeration is impossible.
* Deactivating a user, changing a password, or calling `logout-all` invalidates
  existing access tokens immediately.

### Authorisation

* Every protected route returns `401` without credentials. This is asserted
  route by route, not assumed from a shared dependency.
* Cross-user access returns `404`, never `403`, so the API does not confirm that
  another user's farm, cycle or report exists. Reads, updates and deletes are
  all covered.
* An expense cannot be attached to another user's crop cycle.
* Ownership fields cannot be injected: `user_id` in a farm payload is rejected
  by the strict schema, and `role: "admin"` in a registration payload does not
  produce an admin.

### Injection and input handling

* All database access goes through SQLAlchemy ORM or parameterised queries; no
  string-formatted SQL exists in the backend.
* Hostile strings (`'; DROP TABLE users; --`, `1' OR '1'='1`, null bytes, path
  traversal, script tags) are stored and round-tripped as inert data, and the
  tables survive.
* Numeric fields reject negatives, zero and overflow values with `422`.
* Pagination bounds are enforced server-side.
* Error responses contain no traceback, no SQLAlchemy class names and no
  filesystem paths.

### Report generation and download

* File names are server-generated: no `/`, no `..`, no user-supplied path.
* The `?token=` download link is a short-lived signed token bound to the user
  **and** the report id; a token for report 7 cannot unlock report 8.
* A forged link and an expired report both fail. Credentials presented in the
  header take precedence over a link, so a second user's session cannot borrow
  it.
* Content type is set from a server-side format choice.

### Response hygiene

* `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on every response.
* CORS is an explicit allowlist (`allow_credentials=False`), not `*`.
* The framing policy is configurable (`FRAME_OPTIONS` + `FRAME_ANCESTORS`) only
  so a browser-based development preview can embed the API. The default is
  `DENY`, a matching `frame-ancestors` CSP is emitted whenever it is relaxed,
  and `validate_runtime()` **refuses to boot in production** with anything other
  than `DENY`. Three tests cover the default, the production refusal, and the
  accepted production configuration.
* Origin patterns use `CORS_ORIGIN_REGEX`, never a wildcard in `CORS_ORIGINS`:
  Starlette compares `allow_origins` as literal strings, so `https://*.e2b.app`
  in that list fails the preflight silently rather than opening anything — a
  failure mode that looks like a network error. Tests assert the exact-origin
  path succeeds, the regex path succeeds, an unknown origin is refused, and no
  bare `*` ever appears in `cors_origin_list`.

### Secrets

* No key, token or password literal exists in the repository; no `.env`, `.pem`
  or keystore file holding a real credential is tracked.
* `SECRET_KEY` must be a valid random string in production: the app refuses to
  start with a known placeholder, or with `DEBUG=true`.
* No Google Places key is committed; the buyer search reports
  `source: "unavailable"` rather than pretending to work.

---

## 4. Not covered

Being explicit about the gaps is part of the assessment:

| Not tested | Why | Consequence |
| --- | --- | --- |
| TLS configuration | Terminated by the deployment; no server here has a certificate | Weak TLS (or an absent one) cannot be detected from inside the repo |
| Real device / rooted-device attacks | No Android SDK or device in this environment | Findings 3 and 6 are reasoned, not exploited |
| Penetration test | Out of scope for this phase | Business-logic abuse beyond the scenarios above is unproven |
| Multi-process rate limiting | Single-worker deployment | Finding 5 |
| Chronos model weights | Not loaded (no weights shipped) | The forecasting path is exercised with XGBoost only |
| Load beyond ~200 req/s | Single-process dev server | No capacity number is claimed; see `scripts/load_smoke.py` |

---

## 5. Load smoke test

`scripts/load_smoke.py` runs a fixed read mix for N seconds across concurrent
threads, then fires 40 interleaved expense writes at one crop cycle to prove no
update is lost under concurrency.

Single-process uvicorn, SQLite, 4 threads, 20 s:

```
3927 successful requests in 20.0s = 196.3 req/s

endpoint                                        n     p50     p95     p99     max
reference data (cacheable, hot path)          674     13ms     26ms     41ms     87ms
91-point price series                         619     32ms     59ms     85ms    101ms
multi-table aggregate                         646     21ms     36ms     49ms    108ms
list with derived finance per row             664     21ms     35ms     51ms    103ms
paginated list                                660     14ms     24ms     33ms     84ms
authenticated trivial read                    664     13ms     21ms     28ms     88ms

concurrency: 40 expenses written by 4 threads to one cycle; recorded cost 82000.00 vs expected 82000.00
PASS  no errors, no lost updates, every p95 under 1000 ms
```

Doubling to 8 threads lowers throughput per thread but keeps every p95 under
150 ms, which is the expected shape. **This is a dev-server figure on SQLite; it
is not a production capacity claim.** The numbers to act on are the relative
costs: the price history (91 points plus aggregation) and the derived-finance
list are the two most expensive reads, and both are the ones a cache or an index
would help first.

---

## 6. Test coverage

| Layer | Statements / lines | Notes |
| --- | --- | --- |
| Backend (`app/`) | **87%** (2381 statements) | 161 tests |
| Database (schema + constraints) | **94%** (485 statements) | 45 tests |
| ML source (`evaluation`, `inference`, `models`, `preprocessing`) | **84%** (885 statements) | 85 tests; `training/` excluded because it is a CLI, exercised by the e2e forecast instead |
| Frontend (`src/`) | **70%** lines (934/1326) | 173 tests |

Uncovered backend code is concentrated in the honest-degradation paths that only
run when an external service is misconfigured: `weather_service` (37%),
`ml_client` (33%) and `buyer_service` (72%). Those paths are exercised by the
end-to-end scenario against a mock provider, not by unit tests.

Frontend coverage is lowest in screen render paths; the shared logic
(`utils/`, `services/`, `localization/`) is covered, which is where a defect
would silently corrupt a number.

---

## 7. Reproducing this review

```bash
# dependency advisories
pip install pip-audit
pip-audit -r backend/requirements.txt
cd frontend && npm audit --omit=dev

# application-layer security tests
cd backend && pytest tests/test_security.py -q      # 36 passed
cd frontend && npx jest tests/security.test.js      # 13 passed

# coverage
cd backend  && pytest -q --cov=app --cov-report=term-missing
cd database && pytest tests -q --cov=. --cov-report=term
cd ml       && pytest tests -q --cov=evaluation --cov=inference --cov=models --cov=preprocessing
cd frontend && npx jest --coverage --collectCoverageFrom='src/**/*.{js,jsx}'

# behaviour under load (needs a running API)
python scripts/load_smoke.py --threads 4 --seconds 20
```

## 8. Recommended next steps

Ordered by risk reduction per unit of effort:

1. Move the rate-limit buckets to Redis before any multi-worker deployment.
2. Add `react-native-keychain` (or an encrypted-storage module) for tokens, once
   a device build is possible.
3. Decide finding 4: keep the JWT trade-off, or bump `token_version` on ordinary
   logout and accept signing out all devices.
4. Add certificate pinning for the production API host once it exists.
5. Re-run the dependency scans in CI, so a new advisory fails the build rather
   than being noticed at the next review.
