"""
The actual job execution logic — runs inside the Celery worker (concurrency=1, gpu_training
queue), never in the request/response cycle. This is where architecture doc §7's rules become
real code:

  - GPU is a HARD precondition, checked before anything else. Fails the job with
    GPU_UNAVAILABLE rather than proceeding on CPU — never a silent fallback.
  - Every state transition writes a TrainingEvent row (append-only).
  - On success, a ModelVersion is created and is_latest is flipped atomically.
  - Training itself is NOT reimplemented here — it subprocess-invokes the existing, already
    validated train_forecast.py / train_propensity.py (see
    PHASE1_PHASE2_EXECUTION_FLOW.md's forecasting accuracy-enhancement effort for what these
    scripts already prove works).
"""
import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.datastore.repositories import training_registry_repo as reg
from apps.training.models import FailureReason, ModelVersion, Track, TrainingEvent, TrainingJob


class GPUUnavailableError(Exception):
    pass


def check_gpu_available() -> None:
    """Hard precondition — architecture doc §7.1: never proceed on CPU. Raises rather than
    returning a bool so the caller can't accidentally ignore a False.

    GPU_HEALTH_CHECK_MODE="stub" (only ever set by config/settings/k8s.py, for the
    forecast-api pod that genuinely has no GPU) skips the real torch.cuda subprocess check
    entirely rather than either lying about GPU availability or blocking every job forever.
    It is a named, logged, opt-in mode - never a silent bypass - and every other settings
    module (dev/server/prod) keeps the real check as the default.
    """
    if getattr(settings, "GPU_HEALTH_CHECK_MODE", "required") == "stub":
        return

    python = settings.GPU_TRAINING_PYTHON
    result = subprocess.run(
        [python, "-c", "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)"],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise GPUUnavailableError(
            f"torch.cuda.is_available() returned False or the check failed: "
            f"{result.stderr.decode(errors='replace')[:500]}"
        )


def _log(job: TrainingJob, event_type: str, detail: dict | None = None) -> None:
    TrainingEvent.objects.create(
        job=job, event_type=event_type, detail=detail or {}, gpu_host=job.gpu_host or "",
    )


def _script_for(job: TrainingJob) -> tuple[str, list[str]]:
    """
    ⚠️ BUG FIXED 2026-08-31: job.transform was tracked in the DB and shown in the UI (e.g.
    version label "v1-log1p") but never actually passed to train_forecast.py, which itself
    had no --transform flag to receive it — every forecast job silently trained on raw data
    regardless of what was requested. Both sides are fixed now: train_forecast.py accepts
    --transform, and it's passed here from job.transform (defaulting to RAW if unset, same
    default as the script itself).
    """
    scripts_dir = settings.GPU_TRAINING_SCRIPTS_DIR
    if job.track == Track.FORECAST:
        script = str(Path(scripts_dir) / "train_forecast.py")
        args = ["--target", job.target, "--horizon", "24",
                "--time-limit", "300", "--preset", job.preset,
                "--transform", job.transform or "RAW"]
        return script, args
    script = str(Path(scripts_dir) / "train_propensity.py")
    args = ["--label", job.target, "--time-limit", "300", "--preset", job.preset]
    return script, args


def _meta_path(job: TrainingJob) -> Path:
    out = Path(settings.GPU_TRAINING_OUTPUT_DIR)
    if job.track == Track.FORECAST:
        return out / f"forecast_{job.target}_24h_meta.json"
    return out / f"propensity_{job.target}_meta.json"


def _artifact_path(job: TrainingJob, meta: dict) -> str:
    """Must match the ACTUAL save path each script uses, not a guessed convention — confirmed
    2026-08-31 these differ by track: train_propensity.py saves to models/propensity_<label>,
    but train_forecast.py saves to models/forecast_<target>_<horizon>h (the horizon suffix
    was missing from the first version of this function — never caught because only
    propensity jobs had been run through Django at the time; forecast has no horizon in its
    own naming, so it happened to work by coincidence there)."""
    models_dir = Path(settings.GPU_TRAINING_OUTPUT_DIR).parent / "models"
    if job.track == Track.FORECAST:
        horizon = meta.get("horizon_hours", 24)
        return str(models_dir / f"forecast_{job.target}_{horizon}h")
    return str(models_dir / f"propensity_{job.target}")


def _provenance_for(job: TrainingJob) -> str:
    """PROPENSITY labels are always proxy-derived, hence SIMULATED. FORECAST is REAL except
    for a target explicitly suffixed "_sim" -- a deliberately-separate demo variant trained
    on fabricated data (2026-08-31: test_drive_interest_rate_sim, built when the real target
    turned out too data-starved to validate meaningfully -- see build_sim_test_drive.py). The
    suffix keeps it a distinct (track, target) key so it never collides with or overwrites
    the real is_latest model for the un-suffixed target."""
    if job.track == Track.PROPENSITY:
        return "SIMULATED"
    if job.target.endswith("_sim"):
        return "SIMULATED"
    return "REAL"


def _next_version_label(track: str, target: str, transform: str | None) -> str:
    """v1, v2, v3... per (track, target) — simple incrementing count, matches the
    versioning already established in the closure-run work (v2-log1p / v2-raw)."""
    n = ModelVersion.objects.filter(track=track, target=target).count() + 1
    suffix = f"-{transform.lower()}" if transform else ""
    return f"v{n}{suffix}"


def run_training_job(job_id: int) -> None:
    job = TrainingJob.objects.select_related().get(pk=job_id)
    job.status = "RUNNING"
    job.started_at = timezone.now()
    job.gpu_host = settings.GPU_WORKER_HOST
    job.save(update_fields=["status", "started_at", "gpu_host"])
    _log(job, TrainingEvent.EventType.STARTED, {"track": job.track, "target": job.target})

    try:
        mode = getattr(settings, "GPU_HEALTH_CHECK_MODE", "required")
        _log(job, TrainingEvent.EventType.GPU_HEALTH_CHECK, {"mode": mode})
        check_gpu_available()
    except GPUUnavailableError as e:
        job.status = "FAILED"
        job.failure_reason = FailureReason.GPU_UNAVAILABLE
        job.error_message = str(e)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "error_message", "finished_at"])
        _log(job, TrainingEvent.EventType.FAILED, {"reason": "GPU_UNAVAILABLE", "detail": str(e)})
        return  # never falls through to running on CPU

    script, args = _script_for(job)
    try:
        result = subprocess.run(
            [settings.GPU_TRAINING_PYTHON, script, *args],
            capture_output=True, timeout=1200, text=True,
        )
    except subprocess.TimeoutExpired:
        job.status = "FAILED"
        job.failure_reason = FailureReason.TIMEOUT
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "finished_at"])
        _log(job, TrainingEvent.EventType.FAILED, {"reason": "TIMEOUT"})
        return

    if result.returncode != 0:
        job.status = "FAILED"
        job.failure_reason = FailureReason.WORKER_ERROR
        job.error_message = (result.stderr or "")[-2000:]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "error_message", "finished_at"])
        _log(job, TrainingEvent.EventType.FAILED, {
            "reason": "WORKER_ERROR", "returncode": result.returncode,
            "stderr_tail": (result.stderr or "")[-1000:],
        })
        return

    meta_path = _meta_path(job)
    if not meta_path.exists():
        job.status = "FAILED"
        job.failure_reason = FailureReason.WORKER_ERROR
        job.error_message = f"script exited 0 but {meta_path} was not produced"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "error_message", "finished_at"])
        _log(job, TrainingEvent.EventType.FAILED, {"reason": "missing_meta_output"})
        return

    meta = json.loads(meta_path.read_text())
    score = meta.get("best_score_val", meta.get("test_roc_auc"))
    score = abs(score) if score is not None else None
    metric = meta.get("eval_metric", "roc_auc")

    with transaction.atomic():
        ModelVersion.objects.filter(track=job.track, target=job.target, is_latest=True) \
            .update(is_latest=False)
        version = ModelVersion.objects.create(
            training_job=job,
            track=job.track, target=job.target,
            version_label=_next_version_label(job.track, job.target, job.transform),
            feature_version="1.2",
            transform=job.transform,
            model_name=meta.get("best_model", "unknown"),
            validation_metric=metric,
            validation_score=score if score is not None else 0.0,
            validation_method=meta.get("validation_method", "AutoGluon internal backtest"),
            artifact_path=_artifact_path(job, meta),
            is_latest=True,
            provenance=_provenance_for(job),
            caveat=meta.get("caveat") or "",
        )

        # mirror into SurrealDB's own model_run/prediction tables too — same schema
        # persist_predictions.py already writes, so downstream analytics.py / anything else
        # reading sales_intelligence_model_run keeps working unchanged.
        # NOTE: SurrealDB's DDL (ddl_prediction_model_run.surql) constrains provenance to
        # ['REAL', 'SIMULATED_LABELS'] — a different vocabulary than Django's core.Provenance
        # ('REAL'/'SIMULATED'). Translate at this boundary rather than changing either schema,
        # since real rows already exist under both conventions.
        surreal_provenance = "SIMULATED_LABELS" if version.provenance == "SIMULATED" else "REAL"
        reg.write_model_run({
            "model_run_id": f"django-job-{job.id}",
            "track": job.track.lower(), "target": job.target,
            "model_name": meta.get("best_model", "unknown"),
            "models_trained": meta.get("models_trained", []),
            "leaderboard": meta.get("leaderboard", []),
            "feature_version": "1.2",
            "validation_metric": metric,
            "validation_score": score if score is not None else 0.0,
            "n_rows": meta.get("n_rows"), "n_series": meta.get("n_series"),
            "horizon_hours": meta.get("horizon_hours"),
            "provenance": surreal_provenance,
            "caveat": meta.get("caveat"),
            "trained_at": timezone.now().isoformat(),
        })

    job.status = "SUCCEEDED"
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at"])
    _log(job, TrainingEvent.EventType.SUCCEEDED, {
        "model_version_id": version.id, "version_label": version.version_label,
        "validation_score": version.validation_score,
    })
