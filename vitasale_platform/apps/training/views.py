from django.db import IntegrityError
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import JobStatus, ModelVersion, TrainingJob
from .serializers import (
    ModelVersionSerializer,
    TrainingJobCreateSerializer,
    TrainingJobSerializer,
)
from .tasks import run_training_job_task


class TrainingJobViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                          mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """POST here creates a training job — REJECTED (409) if any job is already QUEUED or
    RUNNING anywhere in the system.

    REVISED 2026-08-31: the original spec ("user should be able to click Train again while
    training is in progress" -> queue it) was explicitly overturned by the user after seeing
    it work exactly as specified — a second click while job 1 was still QUEUED correctly
    created job 2 at queue_position 2, and the user's reaction was "we should not be able to
    click when one training is in pipeline." So: one active job (QUEUED or RUNNING) at a time,
    globally — not per (track, target) — since there is exactly one GPU and the simpler,
    less error-prone UX is a single global lock rather than a queue depth the user has to
    reason about. The Celery gpu_training queue (concurrency=1) still exists as the
    execution-serialization mechanism underneath this, but the API layer now also blocks
    submission before a job would even reach that queue.
    """
    queryset = TrainingJob.objects.prefetch_related("events").all()

    def get_serializer_class(self):
        return TrainingJobCreateSerializer if self.action == "create" else TrainingJobSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        active = TrainingJob.objects.filter(
            status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
        ).order_by("queued_at").first()
        if active is not None:
            return Response(
                {
                    "detail": "A training job is already queued or running. Wait for it to "
                              "finish before starting another.",
                    "active_job": TrainingJobSerializer(active).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job = serializer.save(triggered_by=request.user, status=JobStatus.QUEUED)
        except IntegrityError:
            # the only_one_active_training_job constraint fired — two requests raced past
            # the check above and both tried to insert. This one lost; report it the same
            # way as if the check had caught it, rather than a raw 500.
            active = TrainingJob.objects.filter(
                status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
            ).order_by("queued_at").first()
            return Response(
                {
                    "detail": "A training job is already queued or running. Wait for it to "
                              "finish before starting another.",
                    "active_job": TrainingJobSerializer(active).data if active else None,
                },
                status=status.HTTP_409_CONFLICT,
            )
        run_training_job_task.delay(job.id)

        return Response(TrainingJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self.get_object()
        if job.status != JobStatus.QUEUED:
            return Response(
                {"detail": f"Only QUEUED jobs can be cancelled (this job is {job.status})."},
                status=status.HTTP_409_CONFLICT,
            )
        job.status = JobStatus.CANCELLED
        job.failure_reason = "CANCELLED_BY_USER"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "failure_reason", "finished_at"])
        job.events.create(event_type="CANCELLED", detail={"cancelled_by": request.user.username})
        return Response(TrainingJobSerializer(job).data)


class ModelVersionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    queryset = ModelVersion.objects.all()
    serializer_class = ModelVersionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for param, field in (("track", "track"), ("target", "target")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    @action(detail=True, methods=["post"])
    def promote(self, request, pk=None):
        """Manual override — architecture doc §5.1 screen 6. Same atomic flip the training
        success path uses, just triggered by a person instead of a job completing."""
        from django.db import transaction

        version = self.get_object()
        with transaction.atomic():
            ModelVersion.objects.filter(
                track=version.track, target=version.target, is_latest=True,
            ).update(is_latest=False)
            version.is_latest = True
            version.save(update_fields=["is_latest"])
        return Response(ModelVersionSerializer(version).data)
