import os
import signal

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.datastore.repositories import feature_snapshot_repo, timeseries_repo
from apps.core.models import JobStatus

from .models import PipelineEvent, PipelineMode, PipelineRun
from .serializers import PipelineRunCreateSerializer, PipelineRunSerializer
from .tasks import run_pipeline_task


class PipelineRunViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                          mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Same 'one active run at a time' rule as TrainingJobViewSet, and for a sharper reason
    here: two concurrent BACKFILL/INCREMENTAL/REBUILD runs could race on the same job_state
    watermark and corrupt it, not just contend for a resource. VALIDATE is read-only and
    exempt — matches the model's partial unique constraint exactly."""
    queryset = PipelineRun.objects.prefetch_related("events").all()

    def get_serializer_class(self):
        return PipelineRunCreateSerializer if self.action == "create" else PipelineRunSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data["mode"]

        if mode != PipelineMode.VALIDATE:
            active = PipelineRun.objects.filter(
                status__in=[JobStatus.QUEUED, JobStatus.RUNNING],
            ).exclude(mode=PipelineMode.VALIDATE).order_by("created_at").first()
            if active is not None:
                return Response(
                    {
                        "detail": "A pipeline run is already queued or running. Wait for it "
                                  "to finish before starting another.",
                        "active_run": PipelineRunSerializer(active).data,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            run = serializer.save(triggered_by=request.user, status=JobStatus.QUEUED)
        except IntegrityError:
            active = PipelineRun.objects.filter(
                status__in=[JobStatus.QUEUED, JobStatus.RUNNING],
            ).exclude(mode=PipelineMode.VALIDATE).order_by("created_at").first()
            return Response(
                {
                    "detail": "A pipeline run is already queued or running. Wait for it "
                              "to finish before starting another.",
                    "active_run": PipelineRunSerializer(active).data if active else None,
                },
                status=status.HTTP_409_CONFLICT,
            )

        run_pipeline_task.delay(run.id)
        return Response(PipelineRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """For the 'clicked the wrong button' case — a REBUILD in particular can run for up
        to 30 minutes, and the UI previously offered no way out but waiting.

        This does more than flip a DB flag: pipeline_runner.run_pipeline() now uses Popen
        (not subprocess.run) specifically so the real OS PID of backfill.py/run_features.py
        is recorded on the row, and this action sends that process a real SIGTERM. Without
        this, "cancel" would show CANCELLED in the UI while the actual data-mutating
        subprocess kept running to completion in the background — a worse outcome than no
        cancel button at all, since it would look safe and not be.

        run_pipeline() itself re-checks status after the subprocess exits and will not
        overwrite this CANCELLED write with FAILED just because the kill made it exit non-zero.
        """
        run = self.get_object()
        if run.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return Response(
                {"detail": f"Run is {run.status}, nothing to cancel."},
                status=status.HTTP_409_CONFLICT,
            )

        if run.pid:
            try:
                os.kill(run.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # already exited on its own — fine, we still mark it CANCELLED below

        run.status = JobStatus.CANCELLED
        run.finished_at = timezone.now()
        run.error_message = f"Cancelled by {request.user.username}."
        run.pid = None
        run.save(update_fields=["status", "finished_at", "error_message", "pid"])
        PipelineEvent.objects.create(
            run=run, event_type="CANCELLED", stage=run.current_stage,
            detail={"cancelled_by": request.user.username},
        )

        payload = PipelineRunSerializer(run).data
        if run.mode == PipelineMode.REBUILD:
            # REBUILD deletes feature_snapshot/timeseries before reinserting (run_features.py
            # run_rebuild()) -- cancelling after that delete but before reinsert completes
            # leaves both tables EMPTY. Confirmed by a real incident 2026-09-01 while testing
            # this action: cancelling a REBUILD wiped production data until another
            # Rebuild/Backfill was run to completion. This can't be prevented here (no
            # structured progress signal from the subprocess to know which side of the delete
            # we're on), only surfaced -- any API consumer of this endpoint, not just the
            # frontend's confirm dialog, needs to see this.
            payload["warning"] = (
                "This was a REBUILD — if it had already started deleting old data, "
                "feature_snapshot/timeseries may now be empty. Run another Rebuild or "
                "Backfill to completion to restore them."
            )
        return Response(payload)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """Architecture doc §5.1 screen 3 — sample rows of the new tables after a transform,
        so a bad mapping is caught before it's ever used for training."""
        run = self.get_object()
        limit = int(request.query_params.get("limit", 20))
        return Response({
            "feature_snapshot_sample": feature_snapshot_repo.sample(
                limit=limit, feature_version=run.feature_version),
            "timeseries_sample": timeseries_repo.sample(limit=limit),
        })
