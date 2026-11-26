# Trained artefacts

This directory holds trained model files. **They are not committed to Git.**

## Why

* A `joblib` XGBoost artefact is a few MB per (commodity, market, horizon) pair;
  six series × two horizons is already tens of MB, and it grows with every
  commodity and market added.
* Binary artefacts do not diff, bloat clone times, and go stale the moment the
  data changes. Committing them would make the repository the model store, which
  is the wrong tool.

## Where artefacts come from

```bash
cd ml
python -m training.build_dataset --source datasets/processed/...   # or raw
python -m training.train_all --folds 3
```

`train_all` writes `<model>_<commodity>_<market>_h<horizon>.joblib` here for the
backtest winner of each horizon, and records the filename in
`ml/reports/evaluation.json` so the inference service can find it.

## How to distribute them

| Situation | Method |
| --- | --- |
| Team members working locally | each runs `train_all`; artefacts are reproducible |
| Publishing a release | attach the `.joblib` files to a **GitHub Release** (not the repo) |
| Production deployment | bake them into the ML service image, or mount a volume |
| Large datasets / models | Git LFS is supported but is a last resort; Releases are preferred |

Download instructions for a released artefact set are in
[`../../docs/installation/ml-setup.md`](../../docs/installation/ml-setup.md).

## Naming convention

```
<model>_<commodity-slug>_<market-slug>_h<horizon>.joblib
xgboost_wheat_lahore-sabzi-mandi_h7.joblib
seasonal_naive_potato_multan-mandi_h30.joblib
```

The loader validates the internal feature list, so an artefact produced by an
older feature set fails loudly at load time instead of silently serving a
mismatched model.
