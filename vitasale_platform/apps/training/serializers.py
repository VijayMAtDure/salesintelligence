from rest_framework import serializers

from .models import ModelVersion, TrainingEvent, TrainingJob


class TrainingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingEvent
        fields = ["id", "event_type", "timestamp", "detail", "gpu_host"]


class TrainingJobSerializer(serializers.ModelSerializer):
    queue_position = serializers.ReadOnlyField()
    events = TrainingEventSerializer(many=True, read_only=True)

    class Meta:
        model = TrainingJob
        fields = [
            "id", "track", "target", "transform", "preset", "status",
            "queue_position", "queued_at", "started_at", "finished_at",
            "gpu_host", "failure_reason", "error_message", "events",
        ]
        read_only_fields = [
            "id", "status", "queue_position", "queued_at", "started_at", "finished_at",
            "gpu_host", "failure_reason", "error_message", "events",
        ]


class TrainingJobCreateSerializer(serializers.ModelSerializer):
    """Separate from TrainingJobSerializer: create only accepts the fields a user actually
    chooses — track/target/transform/preset. Everything else (status, timestamps, gpu_host)
    is server-assigned, never client-supplied."""
    class Meta:
        model = TrainingJob
        fields = ["track", "target", "transform", "preset"]


class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelVersion
        fields = [
            "id", "track", "target", "version_label", "feature_version", "transform",
            "model_name", "validation_metric", "validation_score", "validation_method",
            "artifact_path", "is_latest", "provenance", "caveat", "created_at",
            "training_job",
        ]
