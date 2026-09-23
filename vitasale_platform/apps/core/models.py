"""
Shared abstractions used across ingestion/pipeline/training/inference — kept here so the
same job-lifecycle shape isn't redefined four slightly-different ways.

Architecture doc reference: DJANGO_PLATFORM_ARCHITECTURE.md §2 — Postgres is the control
plane (this app and its siblings), SurrealDB stays the actual data store, reached only
through apps/datastore/, never through Django ORM.
"""
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class JobStatus(models.TextChoices):
    """Shared lifecycle for IngestionJob / PipelineRun / TrainingJob / InferenceJob.

    PENDING -> QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED

    Not every job type uses QUEUED meaningfully (only TrainingJob has a real queue — see
    architecture doc §7.2), but sharing one enum keeps status handling in the API/UI uniform
    rather than four almost-identical-but-not-quite status fields.
    """
    PENDING = "PENDING", "Pending"
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Provenance(models.TextChoices):
    """Carried through from the existing pipeline's is_simulated discipline (see
    SIMULATION_REGISTER.md) — every result in this system must be traceable as real or
    simulated. Never let this field go missing on anything user-facing."""
    REAL = "REAL", "Real"
    SIMULATED = "SIMULATED", "Simulated"
