"""
Inference — running a chosen (or latest) model against new input, with an optional
LLM-generated narrative on top (architecture doc §5.2/§6, doc §15's "structured evidence ->
narrative" pattern — the LLM explains, it never invents the underlying numbers).
"""
from django.conf import settings
from django.db import models

from apps.core.models import JobStatus, TimeStampedModel
from apps.training.models import ModelVersion, Track


class InferenceJob(TimeStampedModel):
    track = models.CharField(max_length=20, choices=Track.choices)
    target = models.CharField(max_length=100)

    # Resolved and stored at request time — NOT a live pointer to "whatever is latest now".
    # If "latest" changes tomorrow, this job's result must still show what was actually used.
    model_version = models.ForeignKey(
        ModelVersion, on_delete=models.PROTECT, related_name="inference_jobs",
    )

    input_payload = models.JSONField(
        default=dict, blank=True,
        help_text="Forecast: usually just {horizon_hours}. Propensity: the lead's feature "
                   "values, or a lead_id to look up from the feature store.",
    )

    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    result = models.JSONField(default=dict, blank=True)
    narrative = models.TextField(
        blank=True,
        help_text="Optional OpenAI-generated explanation of `result`. Only ever built from "
                   "the structured result — never given raw chain-of-thought or asked to "
                   "invent numbers not already in `result` (doc §15).",
    )

    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"InferenceJob#{self.pk} {self.track}/{self.target} {self.status}"
