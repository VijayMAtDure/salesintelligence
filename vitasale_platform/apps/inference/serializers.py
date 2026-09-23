from rest_framework import serializers

from apps.training.serializers import ModelVersionSerializer

from .models import InferenceJob


class InferenceJobSerializer(serializers.ModelSerializer):
    model_version = ModelVersionSerializer(read_only=True)

    class Meta:
        model = InferenceJob
        fields = [
            "id", "track", "target", "model_version", "input_payload",
            "status", "started_at", "finished_at", "result", "narrative",
            "error_message", "created_at",
        ]


class InferenceRequestSerializer(serializers.Serializer):
    track = serializers.ChoiceField(choices=["FORECAST", "PROPENSITY"])
    target = serializers.CharField()
    model_version_id = serializers.IntegerField(required=False, allow_null=True)
    input = serializers.DictField(required=False, default=dict)


class NarrativeSandboxSerializer(serializers.Serializer):
    """Dev/test-only: hand-supplied synthetic evidence, no InferenceJob/ModelVersion involved.
    `evidence` must include "target" so TARGET_DESCRIPTIONS/OPERATIONAL_HINTS resolve; for
    FORECAST it's the same shape build_forecast_evidence() produces (forecast_total_p50 etc.),
    for PROPENSITY it's {"target": ..., "probability": ...}."""
    track = serializers.ChoiceField(choices=["FORECAST", "PROPENSITY"])
    provenance = serializers.ChoiceField(choices=["REAL", "SIMULATED"], default="SIMULATED")
    caveat = serializers.CharField(required=False, allow_blank=True, default="")
    evidence = serializers.JSONField()
