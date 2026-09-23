from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.datastore.repositories.feature_snapshot_repo import sample as sample_feature_snapshots
from apps.training.models import ModelVersion

from .models import InferenceJob
from .serializers import InferenceJobSerializer, InferenceRequestSerializer, NarrativeSandboxSerializer
from .tasks import generate_narrative_task, run_inference_task


class InferenceJobViewSet(mixins.CreateModelMixin, mixins.ListModelMixin,
                           mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = InferenceJob.objects.select_related("model_version").all()
    serializer_class = InferenceJobSerializer

    def create(self, request, *args, **kwargs):
        req = InferenceRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        track, target = req.validated_data["track"], req.validated_data["target"]
        version_id = req.validated_data.get("model_version_id")

        if version_id:
            model_version = ModelVersion.objects.filter(pk=version_id).first()
            if model_version is None:
                return Response({"detail": "model_version_id not found"}, status=404)
        else:
            # resolved and stored at request time — NOT a live pointer, so this job's record
            # of "which model was used" stays correct even if "latest" changes later
            model_version = ModelVersion.objects.filter(
                track=track, target=target, is_latest=True,
            ).first()
            if model_version is None:
                return Response(
                    {"detail": f"No trained model exists yet for {track}/{target}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        job = InferenceJob.objects.create(
            track=track, target=target, model_version=model_version,
            input_payload=req.validated_data.get("input", {}),
            triggered_by=request.user, status="QUEUED",
        )
        run_inference_task.delay(job.id)
        return Response(InferenceJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="sample-leads")
    def sample_leads(self, request):
        """Real leads to pick from for a PROPENSITY prediction, so the UI can offer a list
        instead of requiring a hand-typed SurrealDB record id. A handful of identifying
        fields only — this is a picker, not a data browser."""
        limit = int(request.query_params.get("limit", 15))
        rows = sample_feature_snapshots(limit=limit, feature_version="1.2")
        return Response([
            {
                "source_call_decision_id": r.get("source_call_decision_id"),
                "lead_id": r.get("lead_id"),
                "disposition_latest": r.get("disposition_latest"),
                "sentiment_latest": r.get("sentiment_latest"),
                "territory_status": r.get("territory_status"),
            }
            for r in rows
        ])

    @action(detail=True, methods=["post"])
    def narrative(self, request, pk=None):
        job = self.get_object()
        if job.status != "SUCCEEDED":
            return Response(
                {"detail": "Narrative is only available once the prediction has succeeded."},
                status=status.HTTP_409_CONFLICT,
            )
        job.narrative = ""  # clear any previous narrative while regenerating
        job.save(update_fields=["narrative"])
        generate_narrative_task.delay(job.id)
        return Response({"detail": "Generating narrative — poll GET this job for the result."})


class NarrativeSandboxView(APIView):
    """Dev/test-only: exercises the narrative-generation logic (build_forecast_evidence's
    reasoning path, via generate_forecast_narrative / generate_narrative) against hand-built
    synthetic evidence — no InferenceJob or ModelVersion is created, nothing is persisted.
    Exists because the real trained models are frozen against one fixed historical dataset and
    structurally cannot produce every scenario worth testing (e.g. a capacity surplus, a
    shrinking follow-up backlog) — see the 2026-08-31 testing plan (Part 2)."""

    def post(self, request):
        serializer = NarrativeSandboxSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        from apps.inference.services.llm_narrator import (
            LLMNotConfiguredError, generate_forecast_narrative, generate_narrative,
        )

        try:
            if d["track"] == "FORECAST":
                narrative = generate_forecast_narrative(d["evidence"], d["provenance"], d["caveat"])
            else:
                narrative = generate_narrative(d["evidence"], d["provenance"], d["caveat"])
        except LLMNotConfiguredError:
            return Response({"detail": "LLM not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"narrative": narrative})
