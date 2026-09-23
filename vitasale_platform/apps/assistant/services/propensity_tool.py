"""
The assistant's propensity tool -- reuses the exact same inference path the Predict page uses
(apps.inference.services.predictor.run_inference), same synchronous-not-Celery reasoning as
forecast_tool.py. Given one real lead, runs EVERY currently-latest PROPENSITY model against it
in one call -- "trigger models along with current ones" -- rather than requiring a separate
tool call per target. Currently that's label_contacted, label_assigned, and (once trained)
label_test_drive_booked_sim; the list grows automatically as new propensity targets are trained,
no code change needed here when one is added.
"""
from apps.inference.models import InferenceJob
from apps.inference.services.predictor import run_inference
from apps.training.models import ModelVersion, Track


class PropensityUnavailable(Exception):
    pass


def run(source_call_decision_id: str, user) -> dict:
    model_versions = ModelVersion.objects.filter(track=Track.PROPENSITY, is_latest=True)
    if not model_versions:
        raise PropensityUnavailable("no trained propensity models exist yet")

    predictions = {}
    errors = {}
    for mv in model_versions:
        job = InferenceJob.objects.create(
            track=Track.PROPENSITY, target=mv.target, model_version=mv,
            input_payload={"source_call_decision_id": source_call_decision_id},
            triggered_by=user, status="QUEUED",
        )
        run_inference(job.id)
        job.refresh_from_db()

        if job.status != "SUCCEEDED":
            errors[mv.target] = job.error_message or "inference failed for an unknown reason"
            continue

        predictions[mv.target] = {
            "probability": job.result.get("probability"),
            "provenance": mv.provenance,
            "model_version": mv.version_label,
        }

    if not predictions:
        raise PropensityUnavailable(
            f"no propensity model could score this lead: {errors}"
        )

    result = {"source_call_decision_id": source_call_decision_id, "predictions": predictions}
    if errors:
        result["unavailable"] = errors  # e.g. this lead has no feature_snapshot for one target
    return result
