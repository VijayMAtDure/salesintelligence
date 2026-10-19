from django.conf import settings
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.datastore.repositories.ingestion_repo import sample_uploaded_rows
from apps.ingestion.services.csv_loader import compute_checksum

from .models import IngestionJob, IngestionJobType, IngestionMode, UploadedFile
from .serializers import CSVUploadSerializer, DBPullSerializer, IngestionJobSerializer
from .tasks import run_csv_ingestion_task


class IngestionJobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """Read-only for the generic list/retrieve — creation happens through the two dedicated
    actions below (upload_csv / pull_db), since they need different request shapes (a file
    upload vs a mode choice) that don't fit one generic POST /jobs/ body."""
    queryset = IngestionJob.objects.select_related("uploaded_file").prefetch_related("events").all()
    serializer_class = IngestionJobSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ("status", "job_type"):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        return qs

    @action(detail=False, methods=["post"], url_path="upload-csv")
    def upload_csv(self, request):
        if not settings.CSV_UPLOAD_ENABLED:
            return Response(
                {"detail": "CSV upload is temporarily disabled. Use pull-db, or contact an "
                            "administrator if you need file-based ingestion."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        upload_serializer = CSVUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        f = upload_serializer.validated_data["file"]
        target_table = upload_serializer.validated_data["target_table"]

        content = f.read()
        f.seek(0)
        checksum = compute_checksum(content)

        existing = UploadedFile.objects.filter(checksum_sha256=checksum).first()
        if existing is not None:
            # same file already uploaded — no-op, return the existing job(s) rather than
            # re-ingesting duplicate rows (architecture doc §4)
            job = existing.ingestion_jobs.order_by("-created_at").first()
            return Response(
                {"detail": "This exact file was already uploaded — no-op.",
                 "existing_job": IngestionJobSerializer(job).data if job else None},
                status=status.HTTP_200_OK,
            )

        uf = UploadedFile.objects.create(
            file=f, original_filename=f.name, checksum_sha256=checksum,
            target_table=target_table, uploaded_by=request.user,
        )
        job = IngestionJob.objects.create(
            job_type=IngestionJobType.CSV_UPLOAD, uploaded_file=uf,
            triggered_by=request.user, status="QUEUED",
        )
        run_csv_ingestion_task.delay(job.id)
        return Response(IngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="pull-db")
    def pull_db(self, request):
        """Delegates the actual work to apps.pipeline — 'DB pull' has no separate staging
        step of its own, since the source data already lives in SurrealDB; extract.py's own
        queries against it ARE the pull, as the first stage of a normal pipeline run. This
        endpoint exists so the ingestion API surface matches the UI's 'Load Data' screen
        (architecture doc §5.1), which shows CSV and DB options side by side."""
        from apps.pipeline.models import PipelineMode
        from apps.pipeline.views import PipelineRunViewSet

        pull_serializer = DBPullSerializer(data=request.data)
        pull_serializer.is_valid(raise_exception=True)
        mode = pull_serializer.validated_data["mode"]
        pipeline_mode = PipelineMode.REBUILD if mode == "FULL" else PipelineMode.INCREMENTAL

        from django.conf import settings
        pipeline_response = PipelineRunViewSet.as_view({"post": "create"})(
            request._request, data={
                "mode": pipeline_mode, "feature_version": settings.FEATURE_VERSION,
            },
        )
        if pipeline_response.status_code != status.HTTP_201_CREATED:
            return pipeline_response  # 409 if a run is already active — same lock, surfaced here too

        job = IngestionJob.objects.create(
            job_type=IngestionJobType.DB_PULL, mode=mode,
            triggered_by=request.user, status="QUEUED",
            pipeline_run_id=pipeline_response.data["id"],
        )
        return Response(
            {"ingestion_job": IngestionJobSerializer(job).data,
             "pipeline_run": pipeline_response.data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        job = self.get_object()
        if job.job_type != IngestionJobType.CSV_UPLOAD or not job.uploaded_file:
            return Response(
                {"detail": "Preview is only available for CSV_UPLOAD jobs. For DB_PULL, see "
                            "the linked pipeline run's own preview endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = int(request.query_params.get("limit", 20))
        return Response({
            "sample": sample_uploaded_rows(
                job.uploaded_file.target_table, str(job.uploaded_file.id), limit=limit),
        })
