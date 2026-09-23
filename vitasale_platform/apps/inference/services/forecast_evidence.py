"""
Shared evidence-building for FORECAST narratives — used by both the live Predict-page
narrative flow (apps.inference.tasks.generate_narrative_task) and the batch
forecast_dashboard management command, so the two paths can never diverge. Extracted
2026-08-31 specifically so a correctness fix (like the retries_executed sign-interpretation
bug found and fixed the same day) can't regress in one path while staying fixed in the other.
"""
from apps.datastore.surreal_client import get_client
from apps.inference.models import InferenceJob

# ⚠️ CAPACITY_TARGETS REMOVED 2026-09-02: this used to compare calls_attempted/calls_connected/
# new_leads_count against human rep_available x leads_per_rep_per_day capacity — a real domain
# error, confirmed directly by the user. Outbound calling and connecting is done by the
# ElevenLabs AI voice agent, not dealership staff; human reps only get pulled in for a
# confirmed subset of leads (test-drive interest — see OPERATIONAL_HINTS["test_drive_interest_rate"]
# — and Selekt/certified-pre-owned program interest, tracked in call_decision.selekt_interest
# but not currently a forecast target). Comparing AI call volume against human headcount doesn't
# describe a real constraint this dealership manages. No replacement capacity concept added —
# if a real "reps available for test drives" figure exists later, it belongs specifically on
# test_drive_interest_rate's evidence, not a blanket CAPACITY_TARGETS list.
CAPACITY_TARGETS: set[str] = set()


def latest_capacity() -> dict | None:
    rows = get_client().select("SELECT * FROM sales_intelligence_capacity_sim;")
    if not rows:
        return None
    rows.sort(key=lambda r: r["date"])  # never trust SurrealDB ORDER BY for completeness
    return rows[-1]


def summarize_predictions(predictions: list[dict]) -> dict:
    p50s = [p["p50"] for p in predictions]
    p10s = [p["p10"] for p in predictions]
    p90s = [p["p90"] for p in predictions]
    peak = max(predictions, key=lambda p: p["p50"]) if predictions else None
    return {
        "total_p50": round(sum(p50s), 2),
        "total_p10": round(sum(p10s), 2),
        "total_p90": round(sum(p90s), 2),
        "avg_p50_per_hour": round(sum(p50s) / len(p50s), 4) if p50s else 0.0,
        "peak_hour": {"timestamp": peak["timestamp"], "p50": round(peak["p50"], 2)} if peak else None,
    }


def latest_sibling_summary(target: str) -> dict | None:
    """Most recent SUCCEEDED FORECAST InferenceJob result for another target, summarized. A
    single ad-hoc Predict-page run doesn't have sibling forecasts computed in the same batch
    the way forecast_dashboard does, so cross-target comparisons fall back to whatever the
    most recent run for that sibling target was — gracefully omitted if none exists yet."""
    job = (InferenceJob.objects.filter(track="FORECAST", target=target, status="SUCCEEDED")
           .order_by("-created_at").first())
    if not job or not job.result.get("predictions"):
        return None
    return summarize_predictions(job.result["predictions"])


def compare(name_a: str, val_a: float, name_b: str, val_b: float, lower_is_backlog: bool) -> str:
    """Pre-computed, unambiguous plain-language comparison — NEVER hand the LLM a raw signed
    delta and expect it to reason about direction correctly. Confirmed 2026-08-31: the LLM
    misread retries_scheduled(16.2) - retries_executed(204.6) = -188.4 as "executed is below
    scheduled" when executed was actually 12x HIGHER. The arithmetic belongs here, in Python,
    not in the model's head."""
    val_a, val_b = round(val_a, 2), round(val_b, 2)
    if val_a > val_b:
        return f"{name_a} ({val_a}) is HIGHER than {name_b} ({val_b}) by {round(val_a - val_b, 2)}."
    elif val_a < val_b:
        note = " — this signals a backlog building up" if lower_is_backlog else ""
        return f"{name_a} ({val_a}) is LOWER than {name_b} ({val_b}) by {round(val_b - val_a, 2)}{note}."
    return f"{name_a} and {name_b} are equal ({val_a})."


def build_forecast_evidence(job) -> dict:
    """job: an InferenceJob (track=FORECAST, status=SUCCEEDED, result already populated).
    Returns the evidence dict for llm_narrator.generate_forecast_narrative()."""
    target = job.target
    summary = summarize_predictions(job.result["predictions"])
    evidence = {
        "target": target,
        "horizon_hours": job.result.get("horizon_hours", job.input_payload.get("horizon_hours", 24)),
        "model_name": job.result.get("model_name"),
        "forecast_total_p50": summary["total_p50"],
        "forecast_total_p10": summary["total_p10"],
        "forecast_total_p90": summary["total_p90"],
        "peak_hour": summary["peak_hour"],
    }

    if target in CAPACITY_TARGETS:
        capacity = latest_capacity()
        if capacity:
            evidence["capacity_reps_available"] = capacity["reps_available"]
            evidence["capacity_leads_per_rep_per_day"] = capacity["leads_per_rep_per_day"]
            evidence["capacity_total_per_day"] = capacity["total_capacity"]
            evidence["capacity_provenance"] = "SIMULATED"

    if target in ("test_drive_interest_rate", "test_drive_interest_rate_sim"):
        connected = latest_sibling_summary("calls_connected")
        if connected:
            evidence["expected_test_drives"] = round(
                summary["avg_p50_per_hour"] * connected["total_p50"], 2)
            evidence["expected_test_drives_derivation"] = (
                "test_drive_interest_rate (avg/hour, this job) x calls_connected (most recent "
                "forecast total) — both real model outputs, this is arithmetic, not an assumption"
            )

    if target == "purchase_interest_rate":
        yes_count = latest_sibling_summary("purchase_interest_yes_count")
        if yes_count:
            evidence["cross_check_purchase_interest_yes_count_direct_forecast"] = yes_count["total_p50"]

    if target == "retries_executed":
        scheduled = latest_sibling_summary("retries_scheduled")
        if scheduled:
            evidence["scheduled_vs_executed_comparison"] = compare(
                "retries_executed", summary["total_p50"],
                "retries_scheduled", scheduled["total_p50"], lower_is_backlog=True,
            )

    if target == "followups_completed":
        due = latest_sibling_summary("followups_due")
        if due:
            evidence["due_vs_completed_comparison"] = compare(
                "followups_completed", summary["total_p50"],
                "followups_due", due["total_p50"], lower_is_backlog=True,
            )

    return evidence
