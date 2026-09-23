"""
The assistant's forecast tool -- reuses the exact same inference path the Predict page uses
(apps.inference.services.predictor.run_inference), called synchronously instead of via Celery,
since a chat tool call needs its result before the LLM can continue answering. No forecast
logic is duplicated here; this only resolves the latest model and reads back the result shape
apps.inference.services.forecast_evidence already knows how to summarize.
"""
from apps.assistant.catalog import METRICS
from apps.inference.models import InferenceJob
from apps.inference.services.predictor import run_inference
from apps.training.models import ModelVersion, Track

# Every model in this project is trained with prediction_length=24 -- see train_forecast.py.
# predict.py's `--horizon` can only ever TRIM its output to fewer hours, never extend it (fixed
# 2026-09-03: it used to report back whatever horizon was requested regardless of how many
# hours it actually returned -- see predict.py's own fix note). Clamping here, before the call,
# means the model gets an honest, correctly-labeled answer instead of learning about the cap
# only after asking for something too large.
MAX_SUPPORTED_HORIZON_HOURS = 24


class ForecastUnavailable(Exception):
    pass


def run(target: str, horizon_hours: int, user) -> dict:
    if target not in METRICS:
        raise ForecastUnavailable(f"target must be one of {sorted(METRICS)}, got {target!r}")

    requested = horizon_hours
    horizon_hours = min(horizon_hours, MAX_SUPPORTED_HORIZON_HOURS)

    model_version = ModelVersion.objects.filter(
        track=Track.FORECAST, target=target, is_latest=True).first()
    if model_version is None:
        raise ForecastUnavailable(f"no trained model exists yet for target {target!r}")

    job = InferenceJob.objects.create(
        track=Track.FORECAST, target=target, model_version=model_version,
        input_payload={"horizon_hours": horizon_hours}, triggered_by=user, status="QUEUED",
    )
    run_inference(job.id)
    job.refresh_from_db()

    if job.status != "SUCCEEDED":
        raise ForecastUnavailable(job.error_message or "inference failed for an unknown reason")

    preds = job.result.get("predictions", [])
    p50s = [p.get("p50", 0) for p in preds]
    peak = max(preds, key=lambda p: p.get("p50", 0)) if preds else None
    actual_hours = job.result.get("horizon_hours", len(preds))

    result = {
        "target": target,
        "horizon_hours": actual_hours,
        "provenance": model_version.provenance,
        "expected_total": round(sum(p50s), 2),
        "peak_hour": {"timestamp": peak["timestamp"], "value": round(peak["p50"], 2)} if peak else None,
        "model_version": model_version.version_label,
    }
    if requested > actual_hours:
        result["note"] = (
            f"only {actual_hours} hours ahead is supported right now, not the "
            f"{requested} hours asked for -- this covers the next {actual_hours} hours only"
        )
    return result
