"""
Training — the GPU job queue and model registry. This is the direct implementation of
architecture doc §7: every "Train" click creates a new TrainingJob (status=QUEUED), never
rejected; a single GPU worker (Celery, concurrency=1, queue="gpu_training") processes them
strictly in order; every state transition is an append-only TrainingEvent row.
"""
from django.conf import settings
from django.db import models

from apps.core.models import JobStatus, Provenance, TimeStampedModel


class Track(models.TextChoices):
    FORECAST = "FORECAST", "Forecasting"
    PROPENSITY = "PROPENSITY", "Propensity"


class Transform(models.TextChoices):
    """Per-target choice from the log1p-vs-raw closure work (PHASE1_PHASE2_EXECUTION_FLOW.md
    §"Phase 3 — Forecasting accuracy-enhancement effort") — only meaningful for FORECAST."""
    RAW = "RAW", "Raw"
    LOG1P = "LOG1P", "log1p"


class FailureReason(models.TextChoices):
    """Point 6's 'GPU mandatory' rule made concrete: a job that can't get the GPU FAILS with
    this reason, it never silently proceeds on CPU (architecture doc §7.1)."""
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE", "GPU unavailable"
    GPU_HEALTH_CHECK_FAILED = "GPU_HEALTH_CHECK_FAILED", "GPU health check failed"
    DATA_VALIDATION_FAILED = "DATA_VALIDATION_FAILED", "Data validation failed"
    TIMEOUT = "TIMEOUT", "Timeout"
    WORKER_ERROR = "WORKER_ERROR", "Worker error"
    CANCELLED_BY_USER = "CANCELLED_BY_USER", "Cancelled by user"


class TrainingJob(TimeStampedModel):
    track = models.CharField(max_length=20, choices=Track.choices)
    target = models.CharField(
        max_length=100,
        help_text="e.g. 'calls_attempted' (forecast) or 'label_contacted' (propensity).",
    )
    transform = models.CharField(
        max_length=10, choices=Transform.choices, null=True, blank=True,
        help_text="Forecast only. Null for propensity jobs.",
    )
    preset = models.CharField(max_length=50, default="best_quality")

    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    gpu_host = models.CharField(max_length=255, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    failure_reason = models.CharField(max_length=30, choices=FailureReason.choices, blank=True)
    error_message = models.TextField(blank=True)

    # Always 1 on every row — exists solely so the constraint below can express "at most one
    # row with status QUEUED/RUNNING" as a partial unique index (the standard Postgres/Django
    # singleton-row trick: uniqueness on a constant column, scoped by the condition, means at
    # most one row can ever satisfy the condition at once). This is the DB-level backstop for
    # the same rule enforced in TrainingJobViewSet.create() — the view check has a
    # check-then-create race on rapid double-clicks, this constraint closes it.
    _active_lock = models.PositiveSmallIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["queued_at"]  # FIFO — matches the single-worker queue it feeds
        constraints = [
            models.UniqueConstraint(
                fields=["_active_lock"],
                condition=models.Q(status__in=["QUEUED", "RUNNING"]),
                name="only_one_active_training_job",
            ),
        ]

    def __str__(self):
        return f"TrainingJob#{self.pk} {self.track}/{self.target} {self.status}"

    @property
    def queue_position(self):
        """1-indexed position among still-QUEUED jobs, None once it's left the queue.
        Cheap enough at this data volume; revisit if the queue ever gets deep."""
        if self.status != JobStatus.QUEUED:
            return None
        return TrainingJob.objects.filter(
            status=JobStatus.QUEUED, queued_at__lte=self.queued_at,
        ).count()


class TrainingEvent(models.Model):
    """Append-only audit trail — architecture doc §7.4, the literal answer to point 6's
    'events logged in DB... so GPU is properly utilised'. This table IS the GPU utilization
    dashboard's data source."""

    class EventType(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        STARTED = "STARTED", "Started"
        GPU_HEALTH_CHECK = "GPU_HEALTH_CHECK", "GPU health check"
        PROGRESS = "PROGRESS", "Progress"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    detail = models.JSONField(default=dict, blank=True)
    gpu_host = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.job_id}:{self.event_type}@{self.timestamp}"


class ModelVersion(TimeStampedModel):
    """One row per successfully trained model. Two version dimensions kept separate per
    architecture doc §5.3 / doc §14's contract — never collapse feature_version and
    model_version into one field."""
    training_job = models.OneToOneField(
        TrainingJob, on_delete=models.PROTECT, related_name="model_version",
    )
    track = models.CharField(max_length=20, choices=Track.choices)
    target = models.CharField(max_length=100)
    version_label = models.CharField(max_length=50, help_text="e.g. 'v2-log1p'.")
    feature_version = models.CharField(max_length=20)
    transform = models.CharField(
        max_length=10, choices=Transform.choices, null=True, blank=True,
        help_text="FORECAST only. Real field, not just encoded in version_label — inference "
                   "needs to know this to apply the same log1p/expm1 the model was trained "
                   "with, and parsing a display string for that was fragile (bug fixed "
                   "2026-08-31, see job_runner.py's _artifact_path/_script_for comments).",
    )

    model_name = models.CharField(max_length=100, help_text="e.g. 'WeightedEnsemble'.")
    validation_metric = models.CharField(max_length=50, help_text="e.g. 'MASE', 'roc_auc'.")
    validation_score = models.FloatField()
    validation_method = models.CharField(
        max_length=255, blank=True,
        help_text="e.g. '3-window manual rolling backtest, original scale' — precise enough "
                   "that two scores are never compared across incompatible methodologies "
                   "without the difference being visible (see the log1p closure-run writeup).",
    )

    artifact_path = models.CharField(
        max_length=500,
        help_text="Path to the AutoGluon predictor directory. The artifact itself lives on "
                   "disk/object storage, never in this row — doc §13.",
    )
    is_latest = models.BooleanField(default=False)

    provenance = models.CharField(max_length=20, choices=Provenance.choices, default=Provenance.REAL)
    caveat = models.TextField(
        blank=True,
        help_text="Structural/methodological caveats that survive even a passing score — "
                   "see PHASE1_DATA_AND_LOGIC_REFERENCE.md item 11 for why this field exists: "
                   "a caveat must not silently disappear just because a number crossed a "
                   "threshold.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # enforces "at most one is_latest=True per (track, target)" at the DB level —
            # belt-and-suspenders alongside the atomic flip in the promote/train-success logic
            models.UniqueConstraint(
                fields=["track", "target"],
                condition=models.Q(is_latest=True),
                name="one_latest_model_per_track_target",
            ),
        ]

    def __str__(self):
        return f"{self.track}/{self.target} {self.version_label} ({'latest' if self.is_latest else ''})"
