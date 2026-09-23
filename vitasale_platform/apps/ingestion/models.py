"""
Ingestion — CSV upload and DB pull, both converging into the same staged/canonical schema
before the pipeline app touches anything (architecture doc §4).
"""
from django.conf import settings
from django.db import models

from apps.core.models import JobStatus, TimeStampedModel


class UploadedFile(TimeStampedModel):
    """One uploaded CSV. Checksummed so re-uploading the same file is a no-op, not a
    duplicate load (same resumability discipline as the ElevenLabs turn fetch in the
    existing pipeline — see PHASE1_PHASE2_EXECUTION_FLOW.md)."""
    file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    original_filename = models.CharField(max_length=255)
    checksum_sha256 = models.CharField(max_length=64, unique=True)
    target_table = models.CharField(
        max_length=100,
        help_text="Which canonical source table this CSV maps to, e.g. 'call_decision'.",
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    validation_errors = models.JSONField(
        default=list, blank=True,
        help_text="Non-empty means the file was staged but rejected — schema mismatch etc.",
    )

    def __str__(self):
        return f"{self.original_filename} ({self.target_table})"


class IngestionJobType(models.TextChoices):
    CSV_UPLOAD = "CSV_UPLOAD", "CSV upload"
    DB_PULL = "DB_PULL", "Database pull"


class IngestionMode(models.TextChoices):
    """Mirrors the doc's backfill/incremental/rebuild taxonomy (§12.1) — reused, not
    reinvented, per architecture doc §1 point 3."""
    INCREMENTAL = "INCREMENTAL", "Incremental"
    FULL = "FULL", "Full reload"


class IngestionJob(TimeStampedModel):
    job_type = models.CharField(max_length=20, choices=IngestionJobType.choices)
    mode = models.CharField(
        max_length=20, choices=IngestionMode.choices, default=IngestionMode.INCREMENTAL,
        help_text="Only meaningful for DB_PULL; CSV_UPLOAD is always an additive append.",
    )
    uploaded_file = models.ForeignKey(
        UploadedFile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingestion_jobs",
    )
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_ingested = models.PositiveIntegerField(null=True, blank=True)

    # for DB_PULL: what watermark range this run actually covered — same field as
    # sales_intelligence_job_state, mirrored here for control-plane visibility
    watermark_before = models.DateTimeField(null=True, blank=True)
    watermark_after = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)

    # ⚠️ ADDED 2026-09-02: a DB_PULL has no task of its own — pull_db() delegates the real work
    # to a PipelineRun and this row's own status/started_at/finished_at/rows_ingested were then
    # NEVER updated again, so every DB_PULL sat showing "QUEUED" forever in the UI regardless of
    # whether the underlying pull actually succeeded. String reference avoids a circular import
    # (apps.pipeline.models already imports IngestionMode from this module). The live_* properties
    # below read through this link rather than trying to keep two rows in sync after the fact.
    pipeline_run = models.ForeignKey(
        "pipeline.PipelineRun", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingestion_jobs",
        help_text="DB_PULL only — the PipelineRun actually doing the work. Its status/rows are "
                   "authoritative; this job's own status/rows_ingested fields are unused once set.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"IngestionJob#{self.pk} {self.job_type} {self.status}"

    @property
    def live_status(self) -> str:
        return self.pipeline_run.status if self.pipeline_run_id else self.status

    @property
    def live_started_at(self):
        return self.pipeline_run.started_at if self.pipeline_run_id else self.started_at

    @property
    def live_finished_at(self):
        return self.pipeline_run.finished_at if self.pipeline_run_id else self.finished_at

    @property
    def live_error_message(self) -> str:
        return self.pipeline_run.error_message if self.pipeline_run_id else self.error_message

    @property
    def live_rows_ingested(self):
        if not self.pipeline_run_id:
            return self.rows_ingested
        # "events" is the raw row count extracted from the source — the closest match to what
        # "rows ingested" means for a CSV_UPLOAD job; fall back to any other stage if absent.
        rows = self.pipeline_run.rows_processed or {}
        return rows.get("events") or (max(rows.values()) if rows else None)


class IngestionEvent(models.Model):
    """Append-only — never mutated. Direct expression of architecture doc §7.4's event-log
    requirement, applied to ingestion too (not just training)."""
    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    timestamp = models.DateTimeField(auto_now_add=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.job_id}:{self.event_type}@{self.timestamp}"
