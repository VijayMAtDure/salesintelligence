"""
Catalog of what the assistant's query_metric tool is allowed to ask for -- the LLM only ever
picks from these, never invents a table/field/aggregation. See SALES_INTELLIGENCE_AGENT_PLAN.md
§5: the LLM builds a validated spec, Django builds the actual query/computation.

METRICS mirrors vitasale_intelligence/server_scripts/train_forecast.py's TARGETS list (the
real, non-simulated forecast targets) -- kept as its own constant here since Django and the
training scripts are separate codebases with no shared import path. Update both if a target
is added or renamed.

When the knowledge graph is attached later, its concepts get added here too (see the plan
doc's §7) -- this dict growing is the mechanism, not a new subsystem.
"""

METRICS = {
    "calls_attempted": "Number of outbound call attempts",
    "calls_connected": "Number of calls that connected to a live customer",
    "new_leads_count": "Number of new leads entering the pipeline",
    "connect_rate": "Share of attempted calls that connected (0-1)",
    "purchase_interest_rate": "Share of calls where the customer expressed purchase interest (0-1)",
    "purchase_interest_yes_count": "Count of calls with expressed purchase interest",
    "test_drive_interest_rate": "Share of calls expressing test-drive interest (0-1)",
    "retries_scheduled": "Number of re-contact attempts scheduled",
    "retries_executed": "Number of re-contact attempts carried out",
    "followups_due": "Number of follow-up tasks coming due",
    "followups_completed": "Number of follow-up tasks completed",
    "meta_leads_count_sim": "PREVIEW forecast of hourly hyperlocal (Meta/Facebook/Instagram) "
                             "lead volume -- real hyperlocal lead volume is zero so far, so this "
                             "is simulated, not real, and only usable via get_forecast (this "
                             "table has no real historical rows for query_metric to look up).",
}

# ⚠️ Metrics that are proportions (0-1), not counts. Summing a rate across time periods
# produces a number with no real business meaning (e.g. seven days' connect_rate summed to
# "2.8" isn't a rate anymore). Confirmed 2026-09-03: schema-level wording steered the model to
# the right aggregation most of the time but not reliably (it picked sum for
# test_drive_interest_rate once, harmless only because that window's real values happened to
# be all zero) -- same lesson as everywhere else in this project: a prompt-level nudge alone
# isn't a safety guarantee, so this is enforced in query_metric.validate() instead.
RATE_METRICS = {"connect_rate", "purchase_interest_rate", "test_drive_interest_rate"}

# hour_of_day/weekday/is_business_hours are read straight off the stored row -- aggregates.py
# already computes them correctly in IST at write time (see train_forecast.py's
# _business_covariates() writeup for why re-deriving this a third time is exactly the bug
# class to avoid). "date" is the one dimension computed here, from bucket_start + IST offset,
# since no stored column holds it directly.
DIMENSIONS = {
    "hour_of_day": "Group by hour of day, 0-23 (IST)",
    "weekday": "Group by day of week, 0=Monday .. 6=Sunday (IST)",
    "date": "Group by calendar date (IST)",
    "is_business_hours": "Group by whether the hour falls in 9am-7pm IST business hours",
    "total": "NO breakdown -- one single aggregated number for the whole date_range. Use this "
             "for 'what was our overall/average X over period Y' questions, where the answer is "
             "one number, not a per-day/per-hour list. Confirmed 2026-09-22: without this,"
             " the model had to fetch a per-day breakdown and average the rows itself to answer "
             "a single-number question -- unreliable arithmetic, and it also fell back to "
             "listing every individual day instead of giving the one number that was actually "
             "asked for. Use date/hour_of_day/weekday/is_business_hours only when a breakdown "
             "was explicitly asked for (e.g. 'by day', 'which hour', 'compare days').",
}

AGGREGATIONS = {"sum", "avg", "max", "min", "count"}

# "today"/"yesterday" etc. are relative to the latest REAL data point, not wall-clock time --
# this pilot's real data has a fixed historical range, it isn't a live-updating feed at
# chat-query time. See query_metric._date_bounds().
# ⚠️ ADDED 2026-09-22: previous_7_days -- confirmed live: asked "this week vs last week", the
# model had no direct way to get an adjacent, non-overlapping 7-day window (only the ROLLING
# last_7_days/last_30_days existed), so it fetched last_30_days and tried to manually pick "last
# week"'s dates out of a 30-row dump -- exactly the kind of cross-row arithmetic already proven
# unreliable elsewhere (see response_validator.py). A dedicated preset removes the need for that
# arithmetic entirely, the same principle as lead_share/avg_meta_response_minutes.
DATE_RANGE_PRESETS = {"today", "yesterday", "last_7_days", "previous_7_days", "last_30_days",
                       "all_time"}

# --- Lead-level cross-tab catalog (query_lead_outcomes) --------------------------------------
# A DIFFERENT grain from METRICS/DIMENSIONS above: those describe hourly, org-wide aggregates
# from sales_intelligence_timeseries (one row per hour). These describe PER-LEAD outcomes from
# sales_intelligence_feature_snapshot. See apps/assistant/services/query_lead_outcomes.py and
# hyperlocal/HYPERLOCAL_META_LEAD_INTEGRATION.md.
#
# ⚠️ FIXED 2026-09-18: every dimension used to be scoped to hyperlocal (Meta)-sourced leads
# only, via a blanket WHERE clause on the data source -- confirmed live that this made
# genuinely general questions ("which car models book test drives fastest", "which city
# converts best") answer "no data" even though car model/city/email are real and populated for
# the WHOLE lead base (5,383 rows), nothing to do with hyperlocal. Split below into GENERAL
# dimensions (real today, no hyperlocal dependency) and HYPERLOCAL-ONLY ones (genuinely don't
# exist for any other lead source -- correctly empty until real hyperlocal volume exists, not a
# bug).
LEAD_METRICS = {
    "test_drive_scheduled_rate": "Share of leads where a test drive was actually BOOKED/"
                                  "SCHEDULED (real outcome) -- use this one for any 'book'/"
                                  "'booking'/'scheduled' phrasing, not test_drive_interest_rate.",
    "test_drive_interest_rate": "Share of leads that ever expressed test-drive interest during "
                                 "a call -- a weaker, earlier signal than actually booking one. "
                                 "Only 45 of 5,383 real leads (0.84%) have this flag true -- "
                                 "expect small, often-zero groups, not large percentages.",
    "purchase_interest_rate": "Share of leads whose latest purchase interest was YES",
    "avg_meta_response_minutes": "Average real response time in MINUTES (hyperlocal/Meta form "
                                  "submission to our first call) per group -- a raw number, NOT "
                                  "a rate/percentage. Use this, never a rate_pct metric, for "
                                  "'which/how fast responds' or 'fastest'/'slowest' phrasing --"
                                  " confirmed 2026-09-21: asked 'which car model responds "
                                  "fastest', the model substituted test_drive_interest_rate "
                                  "(a completely different, unrelated question -- outcome rate "
                                  "within a response-time bucket, not response speed itself) "
                                  "because no direct timing metric existed. HYPERLOCAL-ONLY, "
                                  "same as meta_response_window_bucket below -- only meaningful "
                                  "for leads with real hyperlocal metadata, and only ~26-32 real "
                                  "leads have it today, so groups will be small.",
    "lead_share": "Use this, and ONLY this, for 'what %/share/fraction/proportion of leads "
                  "have/are/fall into [category]' questions -- e.g. 'what % of leads have "
                  "purchase timeline IMMEDIATE'. This is NOT an outcome metric at all -- it "
                  "carries no rate_pct field, only n/share_pct per group, precisely so there is "
                  "no outcome-rate number sitting nearby to grab by mistake. Confirmed "
                  "2026-09-22: even with a correctly-computed share_pct field present ALONGSIDE "
                  "rate_pct in an outcome-metric result, and explicit instructions to use it, "
                  "the model still read rate_pct instead (reported 'IMMEDIATE timeline: 50%' "
                  "from that group's unrelated 50% purchase-interest rate, when the group's "
                  "real share of all leads was ~0.02%). Routing this question shape to a metric "
                  "with no rate_pct field at all removes that failure mode structurally.",
    "max_meta_response_minutes": "The SLOWEST (maximum) real response time in MINUTES "
                                  "(hyperlocal/Meta form submission to our first call) within a "
                                  "group -- a true maximum, not an average. Use this, never "
                                  "avg_meta_response_minutes, for 'slowest'/'longest'/'worst-"
                                  "case'/'what is the maximum' response-time phrasing. Confirmed "
                                  "2026-09-22: asked 'what is the slowest response time recorded "
                                  "for a hyperlocal lead', the model answered with the AVERAGE "
                                  "(920.8 min) because no true-max metric existed -- the real "
                                  "known outlier is ~20,154 min (a genuine 14-day-late response). "
                                  "HYPERLOCAL-ONLY, same scope as avg_meta_response_minutes.",
    "min_meta_response_minutes": "The FASTEST (minimum) real response time in MINUTES "
                                  "(hyperlocal/Meta form submission to our first call) within a "
                                  "group -- a true minimum, not an average. Use this, never "
                                  "avg_meta_response_minutes, for 'fastest'/'quickest'/'best-"
                                  "case'/'what is the minimum' response-time phrasing. "
                                  "HYPERLOCAL-ONLY, same scope as avg_meta_response_minutes.",
}

# Metrics in this set aggregate a continuous per-lead VALUE (average), not a rate of a boolean
# outcome -- run() branches on this to build sum/count instead of true/unknown per group.
AVERAGE_LEAD_METRICS = {"avg_meta_response_minutes"}

# Metrics in this set report a true MAX or MIN of a continuous per-lead VALUE within a group --
# distinct from AVERAGE_LEAD_METRICS above. Added 2026-09-22 after confirming "slowest response
# time" was being answered with the average because no true-extremum metric existed (see
# max_meta_response_minutes docstring above for the live example).
EXTREME_LEAD_METRICS = {"max_meta_response_minutes", "min_meta_response_minutes"}

# lead_share carries NO outcome/rate at all -- run() skips outcome computation entirely and the
# result has no rate_pct key, by design (see LEAD_METRICS["lead_share"] docstring for why).
SHARE_ONLY_METRICS = {"lead_share"}

LEAD_DIMENSIONS = {
    # --- General -- real for the whole lead base, no hyperlocal dependency -------------------
    "is_hyperlocal": "Group by whether the lead came in through the hyperlocal (Meta/Facebook/"
                      "Instagram) channel at all (True/False) -- real for every lead, computed "
                      "from whether they have a real sales_intelligence_meta_lead record. Use "
                      "THIS, not a meta_*-prefixed dimension, for any 'how many/what rate of "
                      "Meta leads...' question that doesn't need a further breakdown (platform/"
                      "campaign/etc.) -- those specific fields are still empty for all 131 real "
                      "hyperlocal leads today (see meta_platform etc. below), but whether a lead "
                      "IS hyperlocal at all is real and populated right now. Confirmed 2026-09-22: "
                      "asked 'how many Meta leads get interested in test drives', the model "
                      "reached for meta_platform (empty) instead of this simpler, correct "
                      "dimension and got a false 'no data' result for a question that had a real"
                      " answer.",
    "product": "Group by the vehicle model discussed on the call (e.g. XC60, XC90)",
    "city": "Group by the customer's city on their lead record -- e.g. 'which location "
            "converts to test drives the most'. Real for any lead, not hyperlocal-specific.",
    "email_domain_type": "Group by whether the customer's email is a free personal provider "
                          "(gmail/yahoo/etc.) or a business domain -- a plausible fleet/"
                          "corporate-buyer signal. Real for any lead with an email on file "
                          "(76.8% of leads do).",
    "purchase_timeline": "Group by the buying-urgency the customer stated DURING the call "
                          "(IMMEDIATE/NEAR_TERM/LONG_TERM) -- real, but sparse: only 57 of "
                          "5,383 leads have a stated timeline, the rest never discussed it. "
                          "Say so if the group sizes are small, don't just report a rate.",
    "response_speed_bucket": "Group by how fast the customer picked up once we started "
                              "calling (real time_to_first_response_minutes, bucketed same as "
                              "the hyperlocal response window below) -- general responsiveness, "
                              "not specific to any lead source.",
    # --- Hyperlocal-only -- genuinely don't exist for any non-Meta lead ----------------------
    "meta_response_window_bucket": "Group by how fast we made our first call attempt after "
                                    "the hyperlocal (Meta) lead arrived (< 30 min, 30 min - 2h, "
                                    "2h - 24h, > 24h). Only hyperlocal-sourced leads have this.",
    "meta_buying_timeline": "Group by the buying-urgency value the customer selected on the "
                             "hyperlocal lead FORM itself (pre-call, distinct from the general "
                             "purchase_timeline above, which is stated during the call). Only "
                             "hyperlocal-sourced leads have this.",
    "meta_platform": "Group by where the lead form was submitted -- facebook | instagram. "
                      "Only hyperlocal-sourced leads have this.",
    "meta_is_organic": "Group by whether the lead came from the free Page button/post (true) "
                        "or a paid ad (false). Only hyperlocal-sourced leads have this.",
    "meta_campaign_name": "Group by which ad campaign the lead came from -- empty/absent for "
                           "organic leads, only populated once paid ads are actually running. "
                           "Only hyperlocal-sourced leads have this.",
}

# Dimensions with no hyperlocal dependency -- query_lead_outcomes.py uses this to decide
# whether a spec needs at least one hyperlocal-sourced row to answer at all, or can draw on the
# whole real lead base.
GENERAL_LEAD_DIMENSIONS = {"is_hyperlocal", "product", "city", "email_domain_type",
                            "purchase_timeline", "response_speed_bucket"}

# 1 or 2 dimensions -- e.g. ["product", "meta_response_window_bucket"] for "which car models
# close test drives fastest when contacted quickly after a hyperlocal lead" in one query,
# rather than one dimension per question.
MAX_LEAD_GROUP_BY_DIMENSIONS = 2
