from rest_framework import serializers

from .models import IngestionEvent, IngestionJob, UploadedFile


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = [
            "id", "original_filename", "target_table", "row_count",
            "validation_errors", "created_at",
        ]


class IngestionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionEvent
        fields = ["id", "event_type", "timestamp", "detail"]


class IngestionJobSerializer(serializers.ModelSerializer):
    """status/started_at/finished_at/rows_ingested/error_message are read through
    IngestionJob.live_* — for DB_PULL, these reflect the linked PipelineRun's real state
    instead of a value frozen at creation time (see IngestionJob.pipeline_run's docstring)."""
    uploaded_file = UploadedFileSerializer(read_only=True)
    events = IngestionEventSerializer(many=True, read_only=True)
    status = serializers.CharField(source="live_status", read_only=True)
    started_at = serializers.DateTimeField(source="live_started_at", read_only=True)
    finished_at = serializers.DateTimeField(source="live_finished_at", read_only=True)
    rows_ingested = serializers.IntegerField(source="live_rows_ingested", read_only=True)
    error_message = serializers.CharField(source="live_error_message", read_only=True)

    class Meta:
        model = IngestionJob
        fields = [
            "id", "job_type", "mode", "uploaded_file", "status",
            "started_at", "finished_at", "rows_ingested",
            "watermark_before", "watermark_after", "error_message", "events", "created_at",
        ]


class CSVUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    target_table = serializers.CharField()


class DBPullSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["INCREMENTAL", "FULL"], default="INCREMENTAL")
