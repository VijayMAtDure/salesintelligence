from rest_framework import serializers

from .models import PipelineEvent, PipelineRun


class PipelineEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineEvent
        fields = ["id", "stage", "event_type", "timestamp", "detail"]


class PipelineRunSerializer(serializers.ModelSerializer):
    events = PipelineEventSerializer(many=True, read_only=True)

    class Meta:
        model = PipelineRun
        fields = [
            "id", "mode", "feature_version", "status", "current_stage",
            "started_at", "finished_at", "rows_processed", "validation_results",
            "error_message", "events", "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("mode", "feature_version")]


class PipelineRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineRun
        fields = ["mode", "feature_version"]
