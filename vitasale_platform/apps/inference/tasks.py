import logging

from celery import shared_task
from django.utils import timezone

from apps.inference.models import InferenceJob
from apps.inference.services.predictor import run_inference

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_inference_task(self, job_id: int):
    InferenceJob.objects.filter(pk=job_id).update(celery_task_id=self.request.id)
    try:
        run_inference(job_id)
    except Exception as exc:
        logger.exception("Unhandled error running inference job %s", job_id)
        InferenceJob.objects.filter(pk=job_id).update(
            status="FAILED", error_message=f"unhandled: {exc}", finished_at=timezone.now(),
        )
        raise


@shared_task(bind=True)
def generate_narrative_task(self, job_id: int):
    from apps.inference.services.llm_narrator import (
        LLMNotConfiguredError, generate_forecast_narrative, generate_narrative,
    )

    job = InferenceJob.objects.select_related("model_version").get(pk=job_id)
    try:
        if job.track == "FORECAST":
            # Business-actionable narrative (capacity comparisons, cross-target derived
            # counts, a concrete "Recommended action") — added 2026-08-31, previously only
            # available via the forecast_dashboard batch report, now live for every Predict
            # page run too. See forecast_evidence.build_forecast_evidence for what evidence
            # gets attached per target.
            from apps.inference.services.forecast_evidence import build_forecast_evidence
            evidence = build_forecast_evidence(job)
            narrative = generate_forecast_narrative(
                evidence, job.model_version.provenance, job.model_version.caveat,
            )
        else:
            narrative = generate_narrative(
                job.result, job.model_version.provenance, job.model_version.caveat,
            )
        job.narrative = narrative
        job.save(update_fields=["narrative"])
    except LLMNotConfiguredError:
        job.narrative = "(LLM narrative unavailable — no OpenAI API key configured.)"
        job.save(update_fields=["narrative"])
    except Exception as exc:
        logger.exception("Unhandled error generating narrative for job %s", job_id)
        job.narrative = f"(narrative generation failed: {exc})"
        job.save(update_fields=["narrative"])
