"""
Batch orchestration for the "forecast + business-actionable narrative for every target"
request (2026-08-31): runs inference for all 11 documented FORECAST targets against their
latest trained models and generates one narrative per target via generate_forecast_narrative().
Writes the full result to a JSON file for the caller to build a report from.

Evidence-building (capacity comparisons, cross-target derived counts like expected_test_drives,
the retries/followups backlog comparisons) lives in apps.inference.services.forecast_evidence,
shared with the live Predict-page narrative flow (apps.inference.tasks.generate_narrative_task)
so the two paths can never diverge — see that module's docstring for why this matters.

Not otherwise wired into the API/UI — this command is a reporting/testing pass, run via
`manage.py forecast_dashboard`, same spirit as the TEST_RESULTS.csv testing cycle.
"""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.inference.models import InferenceJob
from apps.inference.services.forecast_evidence import (
    build_forecast_evidence, latest_capacity, summarize_predictions,
)
from apps.inference.services.llm_narrator import generate_forecast_narrative
from apps.inference.services.predictor import run_inference
from apps.training.models import ModelVersion

FORECAST_TARGETS = [
    "calls_attempted", "calls_connected", "new_leads_count", "connect_rate",
    "purchase_interest_rate", "purchase_interest_yes_count", "test_drive_interest_rate",
    "retries_scheduled", "retries_executed", "followups_due", "followups_completed",
]
HORIZON_HOURS = 24


class Command(BaseCommand):
    help = "Run forecast inference + business-actionable narratives for all 11 forecast targets."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="/tmp/forecast_dashboard_result.json")

    def handle(self, *args, **opts):
        user = get_user_model().objects.filter(is_superuser=True).first()
        capacity = latest_capacity()
        if capacity:
            self.stdout.write(self.style.NOTICE(
                f"Using capacity_sim row {capacity['id']}: reps_available="
                f"{capacity['reps_available']}, leads_per_rep_per_day="
                f"{capacity['leads_per_rep_per_day']}, total_capacity={capacity['total_capacity']}"
                f" (SIMULATED, date={capacity['date']})"
            ))
        else:
            self.stdout.write(self.style.WARNING("No capacity_sim data found — staffing "
                                                   "comparisons will be omitted."))

        raw, summaries, jobs, narratives, errors = {}, {}, {}, {}, {}

        for target in FORECAST_TARGETS:
            mv = ModelVersion.objects.filter(track="FORECAST", target=target, is_latest=True).first()
            if mv is None:
                errors[target] = "no trained ModelVersion (is_latest=True) found"
                self.stdout.write(self.style.ERROR(f"{target}: SKIPPED — {errors[target]}"))
                continue

            job = InferenceJob.objects.create(
                track="FORECAST", target=target, model_version=mv,
                input_payload={"horizon_hours": HORIZON_HOURS},
                triggered_by=user, status="QUEUED",
            )
            run_inference(job.id)
            job.refresh_from_db()
            if job.status != "SUCCEEDED":
                errors[target] = job.error_message
                self.stdout.write(self.style.ERROR(f"{target}: INFERENCE FAILED — {job.error_message[:200]}"))
                continue

            raw[target] = job.result
            jobs[target] = job
            summaries[target] = summarize_predictions(job.result["predictions"])
            self.stdout.write(self.style.SUCCESS(
                f"{target}: total over {HORIZON_HOURS}h = {summaries[target]['total_p50']} "
                f"(p10 {summaries[target]['total_p10']} / p90 {summaries[target]['total_p90']})"
            ))

        # Narratives — one per target, business-actionable framing. build_forecast_evidence
        # looks up sibling targets' most recent SUCCEEDED job, which (since this loop just
        # created all of them) resolves to the runs above.
        for target, job in jobs.items():
            evidence = build_forecast_evidence(job)
            try:
                narratives[target] = generate_forecast_narrative(
                    evidence, job.model_version.provenance, job.model_version.caveat,
                )
                self.stdout.write(self.style.SUCCESS(f"{target}: narrative generated"))
            except Exception as exc:
                narratives[target] = f"(narrative generation failed: {exc})"
                self.stdout.write(self.style.ERROR(f"{target}: narrative FAILED — {exc}"))

        output = {
            "horizon_hours": HORIZON_HOURS,
            "capacity": capacity,
            "raw": raw,
            "summaries": summaries,
            "narratives": narratives,
            "errors": errors,
        }
        with open(opts["out"], "w") as f:
            json.dump(output, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"Wrote {opts['out']}"))
