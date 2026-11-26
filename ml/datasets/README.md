# Datasets

**Owner:** Member 3 (ML Engineer)

This directory holds **no committed price history**. That is deliberate: the
project must never ship data it cannot license or verify.

```
datasets/
├── raw/          downloaded source files            (git-ignored)
├── processed/    cleaned, feature-ready parquet/CSV (git-ignored)
└── fixtures/     generator + tiny labelled samples  (committed)
```

## Expected schema (the pipeline's contract)

Every source file must be convertible to this CSV/Parquet shape:

| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| `date` | ISO date (`YYYY-MM-DD`) | ✅ | one row per day per series |
| `commodity` | string slug | ✅ | must match `database/seed/001_commodities.sql` slugs (`wheat`, `potato`, …) |
| `market` | string slug | ✅ | must match `database/seed/002_markets.sql` slugs |
| `price_pkr` | float | ✅ | **PKR per 40 kg (maund)**, the mandi quoting convention |
| `source` | string | ✅ | `amis_punjab`, `pbs`, `manual`, `synthetic_fixture` |

Validation is enforced in `preprocessing/loaders.py`; a file that violates the
schema is rejected with a message naming the offending row, rather than silently
producing a wrong model.

## Authoritative sources (Pakistan)

| Source | Publisher | What it provides | Access |
| --- | --- | --- | --- |
| **AMIS Punjab** — Agricultural Marketing Information System | Punjab Agriculture Department | Daily mandi arrival and min/max/avg price per commodity per market | <https://amis.pk> (web portal) |
| **PBS** — Pakistan Bureau of Statistics | Government of Pakistan | Monthly wholesale/retail price indices | <https://www.pbs.gov.pk> |
| **MNFSR / MINFAL** bulletins | Ministry of National Food Security | Seasonal crop and price reports | PDF bulletins |
| Provincial market-committee notices | Each district | Physical/gazetted mandi rates | Boards / PDFs |

**Licensing note:** AMIS and PBS data are published by government bodies for
public information. Before redistributing any extracted dataset in this
repository, confirm the publisher's current terms. When in doubt, keep the file
in `datasets/raw/` (git-ignored) and commit only the *ingestion code* plus
aggregate evaluation results.

## How to add real data

```bash
cd ml
python -m preprocessing.loaders --check path/to/amis_export.csv   # validate only
cp path/to/amis_export.csv datasets/raw/
python -m training.build_dataset --source datasets/raw/amis_export.csv
```

`build_dataset` writes `datasets/processed/prices.parquet` and prints a data
profile (rows, series, date range, missing days, outliers removed).

## The synthetic fixture (and why it exists)

`fixtures/generate_synthetic.py` produces deterministic, **clearly-labelled fake
data** (`source="synthetic_fixture"`) with a trend, weekly and annual
seasonality, and noise. It exists so that:

* the pipeline, models, evaluation harness and service can be tested end to end
  without downloading anything;
* a reviewer can reproduce every number in `docs/ml/evaluation.md`;
* CI stays fast and hermetic.

**It is not, and must never be presented as, observed market history.** Any
metric computed on it measures *whether the code works*, not *how well the model
predicts real prices*. The API and the UI surface the `source` field so a
synthetic series is visibly labelled.

Generate it:

```bash
python -m datasets.fixtures.generate_synthetic --out datasets/raw/synthetic.csv
```
