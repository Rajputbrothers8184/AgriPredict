# Documentation

Start with [`../README.md`](../README.md) for what the project is and
[`../DEVELOPMENT_PROGRESS.md`](../DEVELOPMENT_PROGRESS.md) for what actually
works today — that file is the single source of truth for status, including the
parts that are stubbed or blocked.

## By audience

### I want to use the app

* [User guide](user-guide/README.md) — sign-in, farms, crop cycles, the 40 kg
  maund rule, reading break-even, forecasts, reports, and what each degraded
  state means.

### I want to run it

* **One command:** `make setup` once, then `make`. See
  [Quick start](../README.md#8-quick-start).
* [Installation](installation/README.md) — backend, ML service, Android client,
  demo data, and the emulator/LAN address table, step by step.
* [End-to-end scenario](testing/e2e-scenario.md) — the 71-check acceptance
  walk-through and what each check protects against.

### I want to change it

* [Architecture overview](architecture/overview.md) — why three deployables, why
  finance is derived server-side, why there is no Redux, and what is
  deliberately absent.
* [Financial model](database/financial-model.md) — every derived figure and its
  formula, with the unit convention stated once.
* [API contract](frontend/api-contract.md) — how the frontend's view of the API
  is frozen and regenerated; the rule about widening a schema.
* [ML evaluation](ml/evaluation.md) — models compared, how MAE is measured, and
  why a `synthetic_fixture` MAE validates the pipeline rather than the market.

### I care about safety

* [Security review](security/review.md) — findings, fixes, accepted risks,
  dependency advisories, coverage per layer, and load results.

## Conventions used in these documents

* **Verified / not verified.** Anything stated as working was executed here.
  Anything that cannot be (an APK, a device run, a live weather key) is labelled
  unverified rather than assumed. The current table of unverified items is in
  `frontend/README.md`, section *Not verified*.
* **Units are never implied.** Prices are PKR per **40 kg maund**; sale
  quantities are kilograms. A document that writes a price without its unit is a
  bug in the document.
* **Numbers carry their source.** A test count, a coverage figure or a latency
  figure names the command that produced it.
