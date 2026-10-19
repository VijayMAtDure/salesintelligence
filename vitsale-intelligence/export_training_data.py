"""
Export training datasets from SurrealDB to flat files for the GPU server.

WHY FILES RATHER THAN A LIVE CONNECTION
  SurrealDB runs locally on 127.0.0.1:8000; the GPU box cannot reach it. Training does not
  need live DB access — it needs a frozen, versioned snapshot. Exporting also makes the
  training run reproducible: the exact input is preserved alongside the model.

PRODUCES (doc §7 — "two logical datasets from the same event source")
  1. forecast_<target>.csv  — AutoGluon TimeSeriesDataFrame format
                              (item_id, timestamp, target, + known-future covariates)
  2. propensity.csv         — AutoGluon TabularDataset format
                              (one row per lead-snapshot, features + label)
  3. manifest.json          — row counts, feature_version, provenance, target definitions

⚠️ propensity.csv carries a SIMULATED label (from sales_intelligence_outcome_sim). The
   manifest records this explicitly so nothing downstream can mistake it for real.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

from db import SurrealDB, load_config
from timeutil import parse_iso

OUT = Path(__file__).parent / "data"
# ⚠️ FIXED 2026-09-02: was Path(__file__).parent / "export" -- a directory train_forecast.py
# (scripts/train_forecast.py's DATA = BASE / "data") never reads from. That meant every
# retrain silently trained on whatever was already sitting in data/ (stale since 2026-08-26)
# regardless of how many times export_training_data.py or an incremental pipeline run had
# actually updated the real data -- caught by an end-to-end "add new data, confirm retrain
# reflects it" test that specifically checked n_rows/date-range before and after, not just
# whether the training job reported SUCCEEDED.

# doc §7.1 targets that survived profiling.
# First 3 trained 2026-08-26 (all beat SeasonalNaive). Remaining 6 added same day after a
# full re-audit against the doc found candidates that existed as bucket columns but were
# never tried, plus followups_due/completed/retries which needed new aggregate columns
# (see aggregates.py). qualified_leads/quote_requests/quotes_sent excluded — 18, 0, 0
# events respectively, the same order of sparsity that ruled out the "won" propensity label.
FORECAST_TARGETS = [
    "calls_attempted", "calls_connected", "new_leads_count",             # trained
    "connect_rate", "purchase_interest_rate", "purchase_interest_yes_count",
    "test_drive_interest_rate",                                          # borderline density
    "retries_scheduled", "retries_executed",                             # strong density
    "followups_due", "followups_completed",                              # thin, built per request
]

# doc §7.2 known-future covariates: knowable before the event occurs
KNOWN_COVARIATES = ["hour_of_day", "weekday", "is_business_hours", "active_campaign_count"]

# Feature columns for the propensity model. Deliberately EXCLUDES:
#   - outcome-derived fields (leakage)
#   - identifiers and free text
#   - always-null descoped fields
#   - HOT_LEAD style tags that are CIRCULAR for a "will they buy" question
#     (see FEATURE_DICTIONARY.md — these are defined by test-drive interest upstream)
#
# nba_priority_latest was ORIGINALLY excluded on the same circularity logic, then added back
# 2026-08-26 after a first training run scored a surprisingly weak ROC-AUC (0.58) on
# label_contacted. Root cause: circularity is real for a "will they buy" target, because
# nba_priority is derived from signals that already say the lead looks good. But it is NOT
# circular for "will they be CONTACTED" — priority is what drives rep behaviour (in the
# simulation, literally: CONTACT_RATE is keyed by priority). Excluding it there blinded the
# model to the actual driver of its own label. Lesson: circularity exclusions must be
# evaluated per-target, not applied as one blanket list across every label.
PROPENSITY_FEATURES = [
    "nba_priority_latest",
    # engagement (the validated differentiators)
    "total_turns", "customer_turns", "agent_turns", "interruptions",
    "conversation_duration_secs", "customer_agent_ratio", "engagement_depth",
    "interruption_rate", "turns_per_minute", "avg_silence_before_secs",
    # call volume / cadence
    "calls_total", "calls_connected", "calls_no_response", "connect_rate_lead",
    "re_engagement_count", "calls_per_day_in_pipeline",
    # sentiment
    "sentiment_latest", "sentiment_mean", "sentiment_min", "sentiment_max",
    "sentiment_velocity", "sentiment_recovery",
    # intent
    "purchase_interest_latest", "purchase_interest_velocity", "test_drive_interest_flag",
    # context
    "competitor_mentions", "finance_interest_ever", "territory_status",
    # followups
    "followups_scheduled", "followups_completed", "followup_completion_rate",
    "retries_pending", "followup_latency_minutes",
    # timing / recency
    "days_in_pipeline", "days_since_last_call", "time_to_first_response_minutes",
    "last_customer_gap_minutes", "ai_processing_time_secs",
    # temporal covariates
    "hour_of_day", "weekday", "is_business_hours", "is_weekend",
    "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
    # messaging (sparse but harmless)
    "messages_customer", "messages_agent", "total_interactions",

    # --- added 2026-08-26, accuracy pass -------------------------------------------------
    # assign_rep_flag: same class of bug as nba_priority_latest (fixed earlier the same day).
    # simulate_outcomes.py's own gating logic reads cd.get("assign_rep") directly to decide
    # whether an assignment/contact happens at all — excluding it blinded the model to
    # another direct driver of its own label, not a circular one.
    "assign_rep_flag",
    # legitimate operational signals, confirmed non-circular (they describe AI-side/lead
    # history, not future human rep action), previously excluded with no specific reason:
    "disposition_latest", "escalate_flag", "attempt_number",
    "channel_dominant", "channel_first", "channel_last", "channel_switches",
    "is_multi_channel", "followups_cancelled", "followups_exhausted",
    "whatsapp_sent_count", "nba_completed", "nba_overdue",
    # momentum: doc §10 explicitly wants momentum "validated against actual outcomes" —
    # using it as a propensity feature IS that validation. Not circular: momentum is derived
    # from sentiment/engagement trend, not from contact/assignment.
    "momentum_state", "momentum_score", "momentum_change",
    "top_positive_signal", "top_negative_signal",
]
# Explicitly NOT added: intent_tags_latest / disposition_history (array-typed, CSV encoding
# not worth the complexity this pass), nba_generated (hardcoded to 1 every row — zero
# variance), avg_dealer_response_minutes / outcome / qualification_score / pipeline_velocity
# (confirmed always-null — the exact real data gap this whole exercise is downstream of).

# Hyperlocal (Meta) features, 2026-09-18 -- only ever populated for the ~15% simulated sample
# in sales_intelligence_meta_lead_sim (real sales_intelligence_meta_lead has zero rows today,
# no real hyperlocal leads yet). NONE for every other row -- expected and fine, AutoGluon's
# TabularPredictor already handles sparse/missing columns natively elsewhere in this project.
# Only used for label_test_drive_booked_sim -- see that target's own feature-exclusion note in
# train_propensity.py for why test_drive_interest_flag is dropped specifically there.
PROPENSITY_FEATURES_META = ["meta_to_first_contact_mins", "meta_car_interest", "meta_buying_timeline"]

# Real channel-of-origin flag, 2026-09-21 -- confirmed the real sales_intelligence_meta_lead
# table now has 136 genuine hyperlocal leads (backfilled + validated against the client's Excel
# export, gap < 1 day from lead.created_at). Every OTHER PROPENSITY_FEATURES/META column
# describes call behavior or lead intent, none describe WHERE the lead came from -- confirmed
# earlier this session that no model could distinguish Meta vs. non-Meta leads at all. Unlike
# PROPENSITY_FEATURES_META (simulated, label_test_drive_booked_sim only), this is REAL and goes
# on every target's feature set, same as channel_dominant etc. in PROPENSITY_FEATURES above.
PROPENSITY_FEATURES_REAL_CHANNEL = ["is_hyperlocal"]


def export_forecast(db: SurrealDB) -> dict:
    # ⚠️ DO NOT add ORDER BY to this query. Confirmed 2026-08-26: on this table
    # `SELECT * FROM sales_intelligence_timeseries ORDER BY bucket_start` silently returns
    # 90 of 281 rows — no error, no warning, just missing data. Suspected interaction with
    # the composite unique index (bucket_start, organisation, showroom_id, product_id).
    # call_decision is unaffected (5,383 both ways), so this is table-specific rather than
    # a general SurrealDB behaviour. Sort in Python instead — explicit and safe.
    rows = db.select("SELECT * FROM sales_intelligence_timeseries;")
    rows.sort(key=lambda r: (r["item_id"], parse_iso(r["bucket_start"])))
    written = {}
    for target in FORECAST_TARGETS:
        path = OUT / f"forecast_{target}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["item_id", "timestamp", "target"] + KNOWN_COVARIATES)
            n = 0
            for r in rows:
                # AutoGluon needs a regular series; hourly buckets are IST-aligned so they
                # land on :30 past the UTC hour. Emitting the raw ISO timestamp preserves
                # that regularity.
                w.writerow([
                    r["item_id"],
                    parse_iso(r["bucket_start"]).isoformat(),
                    r.get(target) or 0,
                ] + [r.get(c) for c in KNOWN_COVARIATES])
                n += 1
        written[target] = n
    return written


def export_propensity(db: SurrealDB) -> dict:
    snaps = db.select("SELECT * FROM sales_intelligence_feature_snapshot;")
    outcomes = {o["source_call_decision_id"]: o for o in db.select(
        "SELECT source_call_decision_id, final_outcome, first_contact_at, assigned_at "
        "FROM sales_intelligence_outcome_sim;")}

    # label_test_drive_booked_sim, 2026-09-18: real test_drive_scheduled is too sparse to train
    # on directly (20 of 5,583 real rows, confirmed live) -- same "too sparse" judgment already
    # made for label_won below at a similar order of magnitude. Reuses the EXISTING
    # sales_intelligence_test_drive_booking_sim (simulate_test_drive_bookings.py, built earlier
    # for an unrelated reason) as this label -- no new outcome simulator needed, only the new
    # hyperlocal INPUT simulator (simulate_meta_leads.py).
    booked_sim = {r["source_call_decision_id"]: r.get("test_drive_booked_sim")
                  for r in db.select("SELECT source_call_decision_id, test_drive_booked_sim "
                                     "FROM sales_intelligence_test_drive_booking_sim;")}
    meta_by_lead = {str(r["lead_id"]): r for r in db.select(
        "SELECT lead_id, fb_created_time, car_interest, buying_timeline "
        "FROM sales_intelligence_meta_lead_sim;")}
    real_hyperlocal_lead_ids = {str(r["lead_id"]) for r in
                                 db.select("SELECT lead_id FROM sales_intelligence_meta_lead;")}

    path = OUT / "propensity.csv"
    header = (["source_call_decision_id", "lead_id", "snapshot_at"] + PROPENSITY_FEATURES
              + PROPENSITY_FEATURES_META + PROPENSITY_FEATURES_REAL_CHANNEL
              + ["label_contacted", "label_assigned", "label_won", "label_test_drive_booked_sim"])
    counts = {"rows": 0, "contacted": 0, "assigned": 0, "won": 0, "test_drive_booked_sim": 0,
              "meta_rows": 0, "real_hyperlocal_rows": 0}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for s in snaps:
            o = outcomes.get(s["source_call_decision_id"])
            if not o:
                continue
            contacted = 1 if o.get("first_contact_at") else 0
            assigned = 1 if o.get("assigned_at") else 0
            won = 1 if o.get("final_outcome") == "won" else 0

            booked = booked_sim.get(s["source_call_decision_id"])
            if booked is None:
                continue  # booking-sim doesn't cover this row (shouldn't happen -- it covers
                          # every real snapshot -- but skip rather than write a blank label
            booked_int = 1 if booked else 0

            meta = meta_by_lead.get(str(s["lead_id"]))
            meta_features = []
            if meta is not None:
                delta_mins = round(
                    (parse_iso(s["snapshot_at"]) - parse_iso(meta["fb_created_time"]))
                    .total_seconds() / 60, 1)
                meta_features = [delta_mins, meta.get("car_interest"), meta.get("buying_timeline")]
                counts["meta_rows"] += 1
            else:
                meta_features = [None, None, None]

            is_hyperlocal = 1 if str(s["lead_id"]) in real_hyperlocal_lead_ids else 0

            w.writerow(
                [s["source_call_decision_id"], s["lead_id"], s["snapshot_at"]]
                + [s.get(c) for c in PROPENSITY_FEATURES]
                + meta_features
                + [is_hyperlocal]
                + [contacted, assigned, won, booked_int])
            counts["rows"] += 1
            counts["contacted"] += contacted
            counts["assigned"] += assigned
            counts["won"] += won
            counts["test_drive_booked_sim"] += booked_int
            counts["real_hyperlocal_rows"] += is_hyperlocal
    return counts


def main():
    OUT.mkdir(exist_ok=True)
    cfg = load_config()
    db = SurrealDB(cfg)

    print("exporting forecast datasets...")
    fc = export_forecast(db)
    for t, n in fc.items():
        print(f"  forecast_{t}.csv: {n} rows")

    print("\nexporting propensity dataset...")
    pc = export_propensity(db)
    print(f"  propensity.csv: {pc['rows']} rows")
    print(f"    label_contacted positives: {pc['contacted']}")
    print(f"    label_assigned  positives: {pc['assigned']}")
    print(f"    label_won       positives: {pc['won']}  <- too sparse to train")
    print(f"    label_test_drive_booked_sim positives: {pc['test_drive_booked_sim']}  "
          f"({pc['meta_rows']} rows have real hyperlocal meta features)")
    print(f"    is_hyperlocal=1 (real, all targets): {pc['real_hyperlocal_rows']} rows")

    manifest = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "feature_version": cfg["feature_version"],
        "forecast": {
            "targets": FORECAST_TARGETS,
            "rows": fc,
            "known_covariates": KNOWN_COVARIATES,
            "grain": "organisation/showroom/product x hourly (doc §7)",
            "provenance": "REAL",
        },
        "propensity": {
            "rows": pc["rows"],
            "features": PROPENSITY_FEATURES,
            "meta_features": PROPENSITY_FEATURES_META,
            "meta_rows_populated": pc["meta_rows"],
            "labels": {"contacted": pc["contacted"], "assigned": pc["assigned"],
                       "won": pc["won"],
                       "test_drive_booked_sim": pc["test_drive_booked_sim"]},
            "recommended_target": "label_contacted",
            "provenance": "SIMULATED LABELS",
            "warning": ("Labels come from sales_intelligence_outcome_sim, which is "
                         "fabricated. A 'faster response -> better outcome' relationship "
                         "was built in by construction. Any model result here validates the "
                         "harness ONLY and must not be reported as a finding."),
            "excluded_features_and_why": {
                "nba_priority/sentiment_priority_tags": "circular — defined by test-drive "
                                                          "interest in the upstream prompt",
                "outcome/qualification_score/pipeline_velocity": "always null (descoped)",
                "identifiers/free text": "not model inputs",
            },
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nwrote manifest.json  (feature_version={cfg['feature_version']})")
    print(f"export dir: {OUT}")


if __name__ == "__main__":
    main()
