"""
System Map — the "jungle map" page (2026-09-02): one place answering, end to end, where data
comes from, what's been built, how it's transformed, how many prediction/analysis options
exist, and what's REAL vs SIMULATED everywhere in the platform.

Row counts are queried live (apps.datastore.repositories.system_map_repo) so they never go
stale. Everything else (descriptions, field lists, pipeline stages, options) is static —  it
describes the actual code structure, not runtime data, and doesn't need a live query to stay
accurate; update this file directly when the structure itself changes.
"""
from apps.datastore.repositories import system_map_repo


def _count(table: str) -> int:
    try:
        return system_map_repo.count_table(table)
    except Exception:
        return 0


def compute() -> dict:
    source_tables = [
        {
            "name": "call_decision", "row_count": _count("call_decision"), "provenance": "REAL",
            "description": "The scored NBA record — one row per call, produced by the existing "
                            "scoring pipeline upstream of this platform. The anchor table almost "
                            "everything else joins back to via source_call_decision_id.",
            "fields_used": ["nba_priority", "assign_rep", "test_drive_interest",
                             "test_drive_scheduled", "test_drive_date", "purchase_interest",
                             "purchase_timeline", "selekt_interest", "sentiment_overall",
                             "vehicle_city", "interested_vehicles", "contact_id"],
        },
        {
            "name": "conversation", "row_count": _count("conversation"), "provenance": "REAL",
            "description": "Real customer-agent conversation sessions (ElevenLabs voice).",
            "fields_used": ["turn timing, duration — feeds engagement-depth features"],
        },
        {
            "name": "message", "row_count": _count("message"), "provenance": "REAL",
            "description": "Real turn-level message content within each conversation.",
            "fields_used": ["customer/agent turn counts, sentiment per turn"],
        },
        {
            "name": "campaign_call_log", "row_count": _count("campaign_call_log"), "provenance": "REAL",
            "description": "Real outbound call attempts, retries, answer/end timestamps.",
            "fields_used": ["calls_attempted/calls_connected/retries aggregate counts"],
        },
        {
            "name": "lead", "row_count": _count("lead"), "provenance": "REAL",
            "description": "Real lead lifecycle records.",
            "fields_used": ["lead_id linkage, stage/pipeline context"],
        },
        {
            "name": "lead_nba", "row_count": _count("lead_nba"), "provenance": "REAL",
            "description": "Doc's own NBA-history table — present in the schema but EMPTY in "
                            "this pilot's data; the real NBA priority actually used throughout "
                            "this platform comes from call_decision.nba_priority instead.",
            "fields_used": [],
        },
    ]

    derived_tables = [
        {
            "name": "sales_intelligence_call_event", "row_count": _count("sales_intelligence_call_event"),
            "provenance": "REAL",
            "description": "Canonical normalized event stream — every real call/message/NBA "
                            "event flattened into one common shape (doc §5's event model).",
        },
        {
            "name": "sales_intelligence_call_turn", "row_count": _count("sales_intelligence_call_turn"),
            "provenance": "REAL",
            "description": "Real turn-level conversation detail, one row per customer/agent turn.",
        },
        {
            "name": "sales_intelligence_feature_snapshot", "row_count": _count("sales_intelligence_feature_snapshot"),
            "provenance": "REAL",
            "description": "The lead-level ML feature table — ~92 engineered features per "
                            "real lead (feature_version 1.2). Propensity training input, and "
                            "the source of every REAL number used across Predict/Analytics.",
        },
        {
            "name": "sales_intelligence_timeseries", "row_count": _count("sales_intelligence_timeseries"),
            "provenance": "REAL",
            "description": "Hourly aggregate buckets (org/showroom/product x hour) — the "
                            "forecasting training dataset for all 11 FORECAST targets.",
        },
        {
            "name": "sales_intelligence_model_run", "row_count": _count("sales_intelligence_model_run"),
            "provenance": "REAL",
            "description": "Registry of every training run — model name, metrics, feature/"
                            "model version, mirrored here from Django's own ModelVersion table.",
        },
        {
            "name": "sales_intelligence_prediction", "row_count": _count("sales_intelligence_prediction"),
            "provenance": "REAL",
            "description": "Persisted forecast/propensity outputs — queryable history of "
                            "everything predicted, not just what's shown live.",
        },
        {
            "name": "sales_intelligence_job_state", "row_count": _count("sales_intelligence_job_state"),
            "provenance": "REAL",
            "description": "Incremental-processing watermark — what's already been processed, "
                            "so incremental runs never redo full history.",
        },
        {
            "name": "sales_intelligence_objection", "row_count": _count("sales_intelligence_objection"),
            "provenance": "REAL",
            "description": "REAL objection tags, LLM-extracted from the actual 48,681-word real "
                            "transcript corpus — not yet wired into an Analytics card "
                            "(Product Intelligence, doc use case 7 — next planned build).",
        },
        {
            "name": "sales_intelligence_outcome_sim", "row_count": _count("sales_intelligence_outcome_sim"),
            "provenance": "SIMULATED",
            "description": "Preview NBA-to-assignment-to-contact-to-outcome timing chain "
                            "(seed 20260825) — stands in for real assigned_at/first_contact_at/"
                            "final_outcome, which KIFS hasn't sent yet. Powers NBA Effectiveness "
                            "and Response-Window Intelligence's timing axis.",
        },
        {
            "name": "sales_intelligence_objection_sim", "row_count": _count("sales_intelligence_objection_sim"),
            "provenance": "SIMULATED",
            "description": "Earlier preview objection tags — superseded in practice by the "
                            "real LLM-extracted sales_intelligence_objection table above, kept "
                            "for reference, not used by any live Analytics card.",
        },
        {
            "name": "sales_intelligence_capacity_sim", "row_count": _count("sales_intelligence_capacity_sim"),
            "provenance": "SIMULATED",
            "description": "Preview rep capacity (6 reps x 8 leads/day = 48/day) — powers "
                            "the staffing-gap comparisons in forecast narratives (e.g. "
                            "calls_attempted vs capacity).",
        },
        {
            "name": "sales_intelligence_peer_dealer_sim", "row_count": _count("sales_intelligence_peer_dealer_sim"),
            "provenance": "SIMULATED",
            "description": "A placeholder peer dealer for benchmarking — built early on, then "
                            "explicitly NOT used: comparing against a dealer that doesn't really "
                            "exist would not be a meaningful benchmark. Dealer benchmarking "
                            "stays on hold until a real second showroom exists. Kept only as a "
                            "record of that decision.",
        },
        {
            "name": "sales_intelligence_test_drive_booking_sim", "row_count": _count("sales_intelligence_test_drive_booking_sim"),
            "provenance": "SIMULATED",
            "description": "Preview test-drive bookings (190 of 5,383, seed 20260902), "
                            "correlated with real interest/priority signals — a higher-volume "
                            "comparison for Response-Window Intelligence, kept fully separate "
                            "from the real 20-booking count on call_decision.test_drive_scheduled. "
                            "Reused as-is as label_test_drive_booked_sim's training label below.",
        },
        {
            "name": "sales_intelligence_meta_lead", "row_count": _count("sales_intelligence_meta_lead"),
            "provenance": "REAL",
            "description": "Hyperlocal (Meta/Facebook/Instagram Lead Ads) pre-call metadata, "
                            "2026-09-18 — form-submission timestamp, stated car interest/buying "
                            "timeline, ad/campaign attribution. Zero rows today: real hyperlocal "
                            "leads haven't reached the inbound API yet. Once they do, features.py "
                            "joins this onto feature_snapshot (meta_to_first_contact_mins/"
                            "meta_car_interest/meta_buying_timeline) automatically, no further "
                            "changes needed. See hyperlocal/HYPERLOCAL_META_LEAD_INTEGRATION.md "
                            "for the full field spec.",
        },
        {
            "name": "sales_intelligence_meta_lead_sim", "row_count": _count("sales_intelligence_meta_lead_sim"),
            "provenance": "SIMULATED",
            "description": "Preview hyperlocal lead metadata for ~15% of existing real leads "
                            "(790 rows, seed 20260918), with response-time conditioned on the "
                            "same real signals sales_intelligence_test_drive_booking_sim already "
                            "uses — exists purely so label_test_drive_booked_sim and "
                            "meta_leads_count_sim have something non-degenerate to train on "
                            "before real hyperlocal volume exists. Never touches the real table "
                            "above.",
        },
    ]

    pipeline_stages = [
        {"name": "EXTRACT", "description": "Read raw real records from the source tables above."},
        {"name": "EVENTS", "description": "Normalize into the canonical event stream (sales_intelligence_call_event)."},
        {"name": "FEATURES", "description": "Build the ~92-field lead-level feature snapshot, point-in-time safe (only info available at/before snapshot_at). Also joins hyperlocal (Meta) pre-call metadata where present (meta_to_first_contact_mins/meta_car_interest/meta_buying_timeline), via sales_intelligence_meta_lead -- absent for the vast majority of leads that aren't hyperlocal-sourced, that's expected."},
        {"name": "AGGREGATES", "description": "Roll features up into hourly org/showroom/product buckets (sales_intelligence_timeseries) for forecasting."},
    ]
    pipeline_modes = [
        {"name": "BACKFILL", "description": "Process a full historical date range — used once to populate from empty."},
        {"name": "INCREMENTAL", "description": "Process only what's new/changed since the last watermark (sales_intelligence_job_state)."},
        {"name": "REBUILD", "description": "Recalculate a feature version for a date range — DELETEs feature_snapshot/timeseries first, then re-backfills. Not atomic (a real incident here, found and fixed, is why the Transform page's Cancel button now warns specifically on this mode)."},
        {"name": "VALIDATE", "description": "Read-only quality/leakage checks — writes nothing, exempt from the one-active-run lock, always available."},
    ]

    normalization = [
        {"name": "log1p / expm1 transform", "description": "10 of 11 forecast targets are trained on log1p(count), predictions inverse-transformed via expm1 — chosen per-target from measured MASE improvement (log_transform_experiment.json). retries_executed is the one exception, trained RAW because log1p measurably hurt it there."},
        {"name": "Cyclical time encoding", "description": "hour_of_day/weekday encoded as sin/cos pairs (hour_sin, hour_cos, weekday_sin, weekday_cos) instead of raw integers, so the model sees Saturday-to-Sunday and 23:00-to-00:00 as adjacent, not far apart."},
        {"name": "Known-future covariates", "description": "hour_of_day, weekday, is_business_hours, active_campaign_count — computed identically for training history and the future inference window, so training and inference can never silently drift apart."},
        {"name": "Point-in-time leakage guard", "description": "Every feature in feature_snapshot uses only data available at or before its own snapshot_at — enforced by construction in the feature-builder, not checked after the fact."},
    ]

    flow = {
        "ingestion": {
            "page": "Load Data", "options": [
                "DB pull — INCREMENTAL (since last watermark) or FULL (full reprocess)",
                "CSV upload (target table: call_decision)",
            ],
        },
        "transform": {
            "page": "Transform", "options": [m["name"] for m in pipeline_modes],
            "note": "One active run at a time (VALIDATE exempt) — enforced by a DB constraint, not just the UI. Cancel button available, kills the real OS process.",
        },
        "training": {
            "page": "Train", "options": [
                "Track: FORECAST — 11 real targets + 1 preview (meta_leads_count_sim), transform RAW or LOG1P, GPU-mandatory (AutoGluon TimeSeriesPredictor)",
                "Track: PROPENSITY — 2 real targets (label_contacted, label_assigned) + 1 preview (label_test_drive_booked_sim, blends hyperlocal features), GPU-mandatory (AutoGluon TabularPredictor)",
            ],
            "note": "One active job at a time across both tracks — a second click while one is running is rejected with a 409, not queued.",
        },
        "inference": {
            "page": "Predict", "options": [
                "11 FORECAST targets (24h horizon, P10/P50/P90)",
                "2 PROPENSITY targets (per-lead probability)",
                "2 PREVIEW variants (test_drive_interest_rate_sim, meta_leads_count_sim) — kept visually separate",
            ],
            "note": "Every run auto-fetches an LLM narrative — business-actionable (capacity/backlog comparisons) for FORECAST, evidence-grounded for PROPENSITY.",
        },
        "sandbox": {
            "page": "Sandbox", "description": "Dev/test tool — bypasses trained models entirely, tests the narrative-generation LOGIC against 10 hand-built scenarios (or free-edit JSON). Nothing here is persisted.",
        },
        "analytics": {
            "page": "Analytics", "description": "Doc §9's high-value use cases — pure query/aggregation over the tables above, no model training involved. 3 cards built (NBA Effectiveness, Response-Window real, Response-Window higher-volume preview); see ANALYTICS_ROADMAP.md for the other 5.",
        },
        "assistant": {
            "page": "Assistant (chat)", "options": [
                "query_metric — real historical hourly/org-wide metrics, one group_by dimension",
                "get_forecast — any trained FORECAST target, 24h horizon",
                "query_lead_outcomes — 2026-09-18, per-lead cross-tabs (up to 2 dimensions at once) for hyperlocal leads specifically, e.g. 'which car models close test drives fastest when contacted quickly' — live aggregation, no model",
                "get_lead_propensity — 2026-09-18, one real lead in, every currently-trained PROPENSITY model's prediction out in a single call",
            ],
            "note": "Same 'LLM picks the tool + validated params, Django computes the real answer' discipline as everywhere else — the LLM never writes a query or computes a number itself.",
        },
    }

    # Names kept in sync by hand with frontend/src/pages/InferencePage.tsx's FORECAST_TESTS /
    # PROPENSITY_TESTS / SIM_TEST — this is the authoritative list of what's actually
    # selectable on the Predict page, not a separate guess at it.
    forecast_target_list = [
        {"key": "calls_attempted", "label": "Calls Attempted", "blurb": "Outbound call volume"},
        {"key": "calls_connected", "label": "Calls Connected", "blurb": "Calls that will connect"},
        {"key": "new_leads_count", "label": "New Leads", "blurb": "Leads entering the pipeline"},
        {"key": "connect_rate", "label": "Connect Rate", "blurb": "Share of calls that connect"},
        {"key": "purchase_interest_rate", "label": "Purchase Interest Rate", "blurb": "Share expressing purchase interest"},
        {"key": "purchase_interest_yes_count", "label": "Purchase Interest (Count)", "blurb": "Calls with expressed interest"},
        {"key": "test_drive_interest_rate", "label": "Test-Drive Interest Rate", "blurb": "Share expressing test-drive interest"},
        {"key": "retries_scheduled", "label": "Retries Scheduled", "blurb": "Re-contact attempts queued"},
        {"key": "retries_executed", "label": "Retries Executed", "blurb": "Re-contact attempts carried out"},
        {"key": "followups_due", "label": "Follow-ups Due", "blurb": "Follow-ups coming due"},
        {"key": "followups_completed", "label": "Follow-ups Completed", "blurb": "Follow-ups actually done"},
    ]
    propensity_target_list = [
        {"key": "label_contacted", "label": "Will This Lead Be Contacted?", "blurb": "Probability of a successful contact"},
        {"key": "label_assigned", "label": "Will This Lead Be Assigned?", "blurb": "Probability of rep assignment"},
    ]
    simulated_demo_list = [
        {"key": "test_drive_interest_rate_sim", "label": "Test-Drive Interest Rate (Preview)",
         "blurb": "Denser preview comparison — the real target is too data-sparse to validate meaningfully"},
        {"key": "meta_leads_count_sim", "label": "Hyperlocal Lead Volume (Preview, FORECAST)",
         "blurb": "Real hyperlocal (Meta) lead volume is zero so far — preview only"},
        {"key": "label_test_drive_booked_sim", "label": "Test-Drive Booking Propensity (Preview, PROPENSITY)",
         "blurb": "Blends real base features with preview hyperlocal signal — real test-drive bookings (20 of 5,383) are too sparse to train on directly yet"},
    ]
    analytics_card_list = [
        {"key": "nba_effectiveness", "label": "NBA Effectiveness",
         "blurb": "% acted-on by NBA priority (IMMEDIATE/WITHIN_48_HOURS/SCHEDULED/NO_ACTION)"},
        {"key": "response_window", "label": "Response-Window Intelligence",
         "blurb": "Real bookings/interest by preview contact-timing bucket"},
        {"key": "response_window_sim", "label": "Response-Window — More Volume (Preview)",
         "blurb": "Same breakdown at higher volume, for comparison against the sparse real one"},
    ]

    predictions = {
        "forecast_targets": len(forecast_target_list),
        "propensity_targets": len(propensity_target_list),
        "simulated_demo_variants": len(simulated_demo_list),
        "total_selectable_in_predict_ui": len(forecast_target_list) + len(propensity_target_list) + len(simulated_demo_list),
        "analytics_cards": len(analytics_card_list),
        "forecast_target_list": forecast_target_list,
        "propensity_target_list": propensity_target_list,
        "simulated_demo_list": simulated_demo_list,
        "analytics_card_list": analytics_card_list,
    }

    return {
        "source_tables": source_tables,
        "derived_tables": derived_tables,
        "pipeline_stages": pipeline_stages,
        "pipeline_modes": pipeline_modes,
        "normalization": normalization,
        "flow": flow,
        "predictions": predictions,
    }
