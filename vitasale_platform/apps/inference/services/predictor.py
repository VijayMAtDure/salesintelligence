"""
Runs inference — subprocess-invokes vitasale_intelligence/server_scripts/predict.py against
a real trained model artifact, same reuse pattern as apps.training.services.job_runner.
Lighter-weight than training (a single score, not a fit), so this runs synchronously inside
the Celery task rather than needing its own queue/lock — no GPU exclusivity concern for a
single forward pass at this data volume.
"""
import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.inference.models import InferenceJob

# InferenceJob has no dedicated event model (unlike Training/Pipeline) — results and errors
# are stored directly on the job row, since a single inference call has no meaningful
# multi-stage lifecycle worth logging incrementally.


def run_inference(job_id: int) -> None:
    job = InferenceJob.objects.select_related("model_version").get(pk=job_id)
    job.status = "RUNNING"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    mv = job.model_version
    args = [settings.GPU_TRAINING_PYTHON,
            str(Path(settings.GPU_TRAINING_SCRIPTS_DIR) / "predict.py"),
            "--track", job.track, "--artifact-path", mv.artifact_path]

    if job.track == "PROPENSITY":
        source_id = job.input_payload.get("source_call_decision_id")
        if not source_id:
            job.status = "FAILED"
            job.error_message = "input_payload.source_call_decision_id is required for PROPENSITY"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_message", "finished_at"])
            return
        args += ["--source-call-decision-id", source_id, "--target", job.target]
    else:
        horizon = job.input_payload.get("horizon_hours", 24)
        # must match whatever the resolved model was actually trained with (ModelVersion.
        # transform) — see predict.py's predict_forecast() docstring for the bug this fixes.
        args += ["--target", job.target, "--horizon", str(horizon),
                 "--transform", mv.transform or "RAW"]

    try:
        result = subprocess.run(args, capture_output=True, timeout=300, text=True)
    except subprocess.TimeoutExpired:
        job.status = "FAILED"
        job.error_message = "inference exceeded 5 minute timeout"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return

    if result.returncode != 0:
        job.status = "FAILED"
        job.error_message = (result.stderr or "")[-2000:]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return

    try:
        parsed = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        job.status = "FAILED"
        job.error_message = f"could not parse predict.py output: {result.stdout[-1000:]}"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return

    if "error" in parsed:
        job.status = "FAILED"
        job.error_message = parsed["error"]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return

    job.result = parsed
    job.status = "SUCCEEDED"
    job.finished_at = timezone.now()
    job.save(update_fields=["result", "status", "finished_at"])
