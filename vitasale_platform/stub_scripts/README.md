# stub_scripts/

Placeholders for the real `vitasale_intelligence` scripts (`train_forecast.py`,
`train_propensity.py`, `predict.py`, `backfill.py`, `run_features.py`), which live outside
this repo and are out of scope for the forecast-api k8s pod today — there is no GPU and no
real training-data pipeline on that box.

These exist **only** so the Django-side orchestration — job locking, event trails,
`ModelVersion`/`is_latest` bookkeeping, `InferenceJob` result storage, `PipelineRun`
lifecycle — can be exercised for real against a running pod. Every value they produce is
fabricated and labelled `"STUB"`/`"SIMULATED"` so it can never be mistaken for a real
forecast, score, or feature row.

Only wired up via `config/settings/k8s.py` (`GPU_TRAINING_SCRIPTS_DIR` /
`PIPELINE_SCRIPTS_DIR` default to this directory). `dev.py` / `server.py` / `prod.py` point
at the real scripts and never see this directory.
