"""
Pipeline execution — runs inside the Celery worker on the "pipeline" queue (separate from
gpu_training; this doesn't need the GPU and shouldn't compete for it).

Same reuse strategy as apps.training.services.job_runner: subprocess-invokes the existing,
proven backfill.py / run_features.py rather than reimplementing extract -> events -> features
-> aggregates. Those scripts don't emit a structured meta.json the way the training scripts
do, so row counts are captured by querying the datastore directly after the run, not parsed
from stdout — stdout/stderr are still captured in full as PipelineEvent detail for debugging.
"""
import subprocess
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.datastore.repositories import feature_snapshot_repo, timeseries_repo
from apps.pipeline.models import PipelineEvent, PipelineMode, PipelineRun


def _log(run: PipelineRun, event_type: str, stage: str | None = None, detail: dict | None = None):
    PipelineEvent.objects.create(run=run, event_type=event_type, stage=stage, detail=detail or {})


def _script_for(run: PipelineRun) -> tuple[str, list[str]]:
    """
    ⚠️ REBUILD -> run_features.py --mode rebuild, NOT backfill.py --rebuild. Confirmed by a
    real failure 2026-08-31: backfill.py --rebuild does not DELETE the existing
    sales_intelligence_call_event/feature_snapshot/timeseries rows before re-inserting, so it
    hits a unique-index violation on any table that already has data (i.e. every real
    rebuild, since rebuild-on-an-empty-table is just a backfill). run_features.py's
    run_rebuild() explicitly DELETEs all three tables first, then calls the same
    backfill.run_backfill() underneath — that's the actually-safe path, and it's the one
    this project used for its real v1.0->v1.1->v1.2 feature-version bumps earlier this
    session. The failure was caught safely (unique-index enforcement rejected the collision,
    corrupted nothing — verified by exact row-count match afterward) but the wrong script was
    being invoked for this mode.
    """
    scripts_dir = settings.PIPELINE_SCRIPTS_DIR
    if run.mode == PipelineMode.BACKFILL:
        return str(Path(scripts_dir) / "backfill.py"), []
    if run.mode == PipelineMode.REBUILD:
        return (str(Path(scripts_dir) / "run_features.py"),
                ["--mode", "rebuild", "--feature-version", run.feature_version])
    if run.mode == PipelineMode.INCREMENTAL:
        return str(Path(scripts_dir) / "run_features.py"), ["--mode", "incremental"]
    if run.mode == PipelineMode.VALIDATE:
        return str(Path(scripts_dir) / "run_features.py"), ["--mode", "validate"]
    raise ValueError(f"unknown pipeline mode: {run.mode}")


def _was_cancelled(run_id: int) -> bool:
    """Re-reads current DB status — the cancel action (apps.pipeline.views.PipelineRunViewSet
    .cancel) writes CANCELLED directly and kills the subprocess by PID from OUTSIDE this
    function (a separate request/response cycle), so this function's own status write must
    defer to that rather than overwrite it with FAILED just because SIGTERM made the
    subprocess exit non-zero."""
    return PipelineRun.objects.filter(pk=run_id, status="CANCELLED").exists()


def run_pipeline(run_id: int) -> None:
    if _was_cancelled(run_id):
        # cancelled between QUEUED and Celery actually picking this up -- never spawn.
        return

    run = PipelineRun.objects.get(pk=run_id)
    run.status = "RUNNING"
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])
    _log(run, "STARTED", detail={"mode": run.mode})

    script, args = _script_for(run)
    proc = subprocess.Popen(
        [settings.PIPELINE_PYTHON, script, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=settings.PIPELINE_SCRIPTS_DIR,
    )
    # Save the real PID immediately so a cancel request arriving mid-run has something to
    # signal — this is the whole point of Popen over subprocess.run() here.
    PipelineRun.objects.filter(pk=run_id).update(pid=proc.pid)

    try:
        stdout, stderr = proc.communicate(timeout=1800)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        if _was_cancelled(run_id):
            return
        run.status = "FAILED"
        run.error_message = "pipeline run exceeded 30 minute timeout"
        run.finished_at = timezone.now()
        run.pid = None
        run.save(update_fields=["status", "error_message", "finished_at", "pid"])
        _log(run, "FAILED", detail={"reason": "TIMEOUT"})
        return

    if _was_cancelled(run_id):
        # cancel action already killed the process and wrote the terminal state -- just log
        # the tail output for debugging and stop, don't touch status.
        _log(run, "SCRIPT_OUTPUT", detail={
            "returncode": proc.returncode,
            "stdout_tail": (stdout or "")[-4000:],
            "stderr_tail": (stderr or "")[-2000:],
            "note": "process was cancelled by user request",
        })
        return

    _log(run, "SCRIPT_OUTPUT", detail={
        "returncode": proc.returncode,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-2000:],
    })

    if proc.returncode != 0:
        run.status = "FAILED"
        run.error_message = (stderr or "")[-2000:]
        run.finished_at = timezone.now()
        run.pid = None
        run.save(update_fields=["status", "error_message", "finished_at", "pid"])
        _log(run, "FAILED", detail={"returncode": proc.returncode})
        return

    # row counts queried post-run, not parsed from stdout — see module docstring
    rows_processed = {
        "feature_snapshot": feature_snapshot_repo.count(feature_version=run.feature_version),
        "timeseries": timeseries_repo.count(),
    }
    run.rows_processed = rows_processed
    run.status = "SUCCEEDED"
    run.finished_at = timezone.now()
    run.current_stage = "AGGREGATES" if run.mode != PipelineMode.VALIDATE else None
    run.pid = None
    run.save(update_fields=["rows_processed", "status", "finished_at", "current_stage", "pid"])
    _log(run, "SUCCEEDED", detail=rows_processed)
