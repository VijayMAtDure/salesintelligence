"""
Pipeline — the events -> features -> aggregates transform, orchestrating the existing
events.py / features.py / aggregates.py logic (unchanged) behind an API instead of a CLI.
"""
from django.conf import settings
from django.db import models

from apps.core.models import JobStatus, TimeStampedModel
from apps.ingestion.models import IngestionMode  # reuse INCREMENTAL/FULL — same taxonomy


class PipelineMode(models.TextChoices):
    """Matches doc §12.1 modes exactly: backfill/incremental/rebuild/validate. FORECAST mode
    from the doc lives in apps.training instead (it's a training-track concern, not a
    transform-stage one)."""
    BACKFILL = "BACKFILL", "Backfill"
    INCREMENTAL = "INCREMENTAL", "Incremental"
    REBUILD = "REBUILD", "Rebuild"
    VALIDATE = "VALIDATE", "Validate (no writes)"


class PipelineStage(models.TextChoices):
    EXTRACT = "EXTRACT", "Extract"
    EVENTS = "EVENTS", "Normalize into events"
    FEATURES = "FEATURES", "Feature snapshots"
    AGGREGATES = "AGGREGATES", "Hourly aggregates"


class PipelineRun(TimeStampedModel):
    mode = models.CharField(max_length=20, choices=PipelineMode.choices)
    feature_version = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    current_stage = models.CharField(
        max_length=20, choices=PipelineStage.choices, null=True, blank=True,
        help_text="Stage in progress, or last stage completed if status is terminal.",
    )
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # row counts per stage, e.g. {"events": 37732, "features": 5383, "aggregates": 293}
    rows_processed = models.JSONField(default=dict, blank=True)

    # validation results when mode=VALIDATE or as a post-run check — mirrors validation.py's
    # existing checks (reconciliation / leakage / idempotency / sparsity)
    validation_results = models.JSONField(default=dict, blank=True)

    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    # The actual OS PID of the running backfill.py/run_features.py subprocess — set the
    # moment it's spawned (services/pipeline_runner.py), used by the cancel action to send a
    # real SIGTERM. Without this, "cancel" could only ever flip a DB flag while the real
    # subprocess kept mutating data in the background — see cancel action docstring.
    pid = models.PositiveIntegerField(null=True, blank=True)

    # Same "at most one active row" trick as TrainingJob._active_lock — see that model's
    # comment for the full mechanism. Even MORE important here than for training: two
    # concurrent pipeline runs could race on the same job_state watermark and corrupt it,
    # not just contend for a resource. VALIDATE mode (read-only) is deliberately excluded
    # from the lock — it writes nothing, so it can safely run alongside anything.
    _active_lock = models.PositiveSmallIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["_active_lock"],
                condition=models.Q(status__in=["QUEUED", "RUNNING"]) & ~models.Q(mode="VALIDATE"),
                name="only_one_active_pipeline_run",
            ),
        ]

    def __str__(self):
        return f"PipelineRun#{self.pk} {self.mode} {self.status} ({self.current_stage})"


class PipelineEvent(models.Model):
    run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="events")
    stage = models.CharField(max_length=20, choices=PipelineStage.choices, null=True, blank=True)
    event_type = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.run_id}:{self.event_type}@{self.timestamp}"
