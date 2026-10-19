"""
Stage 5 — Forecasting aggregates -> sales_intelligence_timeseries.
Reads sales_intelligence_call_event (Stage 2 output) directly — independent of features.py.

GRAIN (doc §7): organisation / showroom / product x fixed time bucket.
FREQUENCY (doc §8): 1 hour initially; 30 minutes only if sufficiently dense.

Revised 2026-08-21 from the original (date x organisation x campaign_id, daily):
  - daily -> hourly. Daily gave only 11 usable points across a 20-day span with two
    multi-day gaps — unusable for any horizon. Hourly gives ~84 active buckets and there
    is a real hour-of-day pattern (11:00-18:00 IST, peak 15:00-16:00).
  - campaign_id removed as a series key. It is not in the doc's grain, and splitting by it
    fragmented already-thin data into 13 series of <=6 points each — exactly what doc §20
    warns against ("do not force sparse ... time series"). Campaign is now a known-future
    covariate column (active_campaign_count) per doc §7.2 instead.
  - showroom_id / product_id added as series keys per the doc.
  - rate targets added alongside volumes (see below).

PRODUCT ATTRIBUTION: a CALL_ATTEMPTED event carries no product — product is only known once
call_decision resolves interested_vehicles. All events of a call are therefore attributed to
the product that call ultimately resolved to; otherwise volumes and outcomes would land in
different series. Calls that never resolve a product get product_id = None (the dense
"unknown product" series).

RATE TARGETS: these calls are outbound and batch-triggered — an operator launching a campaign
batch fires 1,000+ calls, so raw volume partly measures operator scheduling rather than
customer demand (the 6-day gap and the 8-call day are operational, not demand signals).
Rates (connect / test-drive-interest / purchase-interest per bucket) are demand-side and
independent of batch timing, so they are the more genuinely forecastable targets.
"""
from collections import defaultdict
from zoneinfo import ZoneInfo

from extract import PILOT_START
from timeutil import parse_iso, parse_utc

IST = ZoneInfo("Asia/Kolkata")


def _hour_bucket(event_timestamp: str):
    """Truncate to the hour, in business timezone (doc §20: preserve organisation business
    timezone for business-hour features)."""
    dt = parse_iso(event_timestamp).astimezone(IST)
    return dt.replace(minute=0, second=0, microsecond=0)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def build_hourly_buckets(call_events: list[dict], feature_version: str,
                          showroom_id: str, business_hours_cfg: dict,
                          product_by_call_response: dict | None = None) -> list[dict]:
    """One row per (bucket_start, organisation, showroom_id, product_id).
    product_by_call_response maps call_response_id -> product_id (resolved from the call's
    call_decision); used to attribute every event of a call to a single product series."""
    product_by_call_response = product_by_call_response or {}
    pilot_start_dt = parse_utc(PILOT_START)

    buckets = defaultdict(lambda: {
        "calls_attempted": 0, "calls_connected": 0,
        "disposition_counts": defaultdict(int),
        "test_drive_interest_yes_count": 0, "purchase_interest_yes_count": 0,
        "escalate_count": 0, "decisions_scored": 0,
        "talk_durations": [], "campaign_ids": set(),
        # added 2026-08-26 as forecast-target candidates (doc §7.1 followups_due /
        # followups_completed). Retries counted alongside since they share the same event
        # types and turned out to have far healthier volume (~5,500 each vs ~200).
        "followups_due": 0, "followups_completed": 0,
        "retries_scheduled": 0, "retries_executed": 0,
    })

    # first-ever attempt per lead -> new_leads_count
    first_attempt_bucket_by_lead = {}
    for ev in call_events:
        if ev["event_type"] != "CALL_ATTEMPTED":
            continue
        if parse_iso(ev["event_timestamp"]) < pilot_start_dt:
            continue
        b = _hour_bucket(ev["event_timestamp"])
        lead_id = ev["lead_id"]
        if lead_id not in first_attempt_bucket_by_lead or b < first_attempt_bucket_by_lead[lead_id]:
            first_attempt_bucket_by_lead[lead_id] = b
    new_leads_by_bucket = defaultdict(set)

    def product_for(ev):
        """Resolve this event's product via its own call_response_id, or via the
        call_decision's parent call_response for CALL_DECISION_SCORED events.

        ⚠️ PERMANENT LIMITATION (confirmed 2026-08-27, not fixable without a risky fuzzy
        join): CALL_ATTEMPTED (source_table=campaign_call_log), RETRY_SCHEDULED/EXECUTED
        (source_table=scheduled_event), and FOLLOWUP_SCHEDULED/EXECUTED
        (source_table=campaign_followup) can NEVER resolve a product here — none of those
        source tables carry a call_response_id, only lead_id, and a lead can have multiple
        calls across different products, so there is no clean join back.

        Practical consequence: calls_attempted, retries_scheduled, retries_executed,
        followups_due, followups_completed, and new_leads_count are PERMANENTLY confined to
        the single product_id=None ("UNKNOWN") series — not a data-volume problem, and not
        fixable by accumulating more history (real or simulated) on the product-level
        series. This was misdiagnosed once as a data-volume/cross-series-learning gap before
        this was traced; see PHASE1_DATA_AND_LOGIC_REFERENCE.md item 11 for the full story
        and why these specific targets underperform naive-baseline forecasting even under
        heavy model tuning (best_quality preset) — they are closer to operator-scheduling
        decisions than smooth customer-demand patterns, and no amount of series depth
        changes that.
        """
        if ev["source_table"] == "call_response":
            return product_by_call_response.get(ev["source_id"])
        if ev["source_table"] == "call_decision":
            return product_by_call_response.get((ev.get("payload") or {}).get("callResponseId"))
        return None

    for ev in call_events:
        # guard against stray pre-pilot timestamps (see reference doc §6 item 6)
        if parse_iso(ev["event_timestamp"]) < pilot_start_dt:
            continue

        et = ev["event_type"]
        if et not in ("CALL_ATTEMPTED", "CALL_CONNECTED", "CALL_DECISION_SCORED",
                      "FOLLOWUP_SCHEDULED", "FOLLOWUP_EXECUTED",
                      "RETRY_SCHEDULED", "RETRY_EXECUTED"):
            continue

        bucket_start = _hour_bucket(ev["event_timestamp"])
        product_id = product_for(ev)
        key = (bucket_start, ev["organisation"], showroom_id, product_id)
        b = buckets[key]
        if ev.get("campaign_id"):
            b["campaign_ids"].add(ev["campaign_id"])

        if et == "CALL_ATTEMPTED":
            b["calls_attempted"] += 1
            if first_attempt_bucket_by_lead.get(ev["lead_id"]) == bucket_start:
                new_leads_by_bucket[key].add(ev["lead_id"])

        elif et == "CALL_CONNECTED":
            b["calls_connected"] += 1
            talk = (ev["payload"] or {}).get("talkDuration")
            if talk is not None:
                b["talk_durations"].append(talk)

        elif et == "CALL_DECISION_SCORED":
            cd = ev["payload"] or {}
            b["decisions_scored"] += 1
            if cd.get("disposition_tag"):
                b["disposition_counts"][cd["disposition_tag"]] += 1
            if cd.get("test_drive_interest") == "YES":
                b["test_drive_interest_yes_count"] += 1
            if cd.get("purchase_interest") == "YES":
                b["purchase_interest_yes_count"] += 1
            if cd.get("escalate"):
                b["escalate_count"] += 1

        elif et == "FOLLOWUP_SCHEDULED":
            b["followups_due"] += 1
        elif et == "FOLLOWUP_EXECUTED":
            b["followups_completed"] += 1
        elif et == "RETRY_SCHEDULED":
            b["retries_scheduled"] += 1
        elif et == "RETRY_EXECUTED":
            b["retries_executed"] += 1

    rows = []
    for (bucket_start, organisation, shwrm, product_id), b in buckets.items():
        attempted, connected = b["calls_attempted"], b["calls_connected"]
        scored = b["decisions_scored"]
        weekday = bucket_start.weekday()
        rows.append({
            # --- series keys (doc §7 grain) ---
            "bucket_start": bucket_start.isoformat(),
            "bucket": "hourly",
            "organisation": organisation,
            "showroom_id": shwrm,
            "product_id": product_id,
            # AutoGluon item_id — one string identifying the series
            "item_id": f"{organisation}|{shwrm}|{product_id or 'UNKNOWN'}",
            # --- volume targets ---
            "calls_attempted": attempted,
            "calls_connected": connected,
            "calls_no_response": max(0, attempted - connected),
            "decisions_scored": scored,
            "disposition_counts": dict(b["disposition_counts"]),
            "test_drive_interest_yes_count": b["test_drive_interest_yes_count"],
            "purchase_interest_yes_count": b["purchase_interest_yes_count"],
            "escalate_count": b["escalate_count"],
            "followups_due": b["followups_due"],
            "followups_completed": b["followups_completed"],
            "followup_completion_rate": _safe_rate(b["followups_completed"], b["followups_due"]),
            "retries_scheduled": b["retries_scheduled"],
            "retries_executed": b["retries_executed"],
            "new_leads_count": len(new_leads_by_bucket.get(
                (bucket_start, organisation, shwrm, product_id), ())),
            "avg_talk_duration_seconds": (
                round(sum(b["talk_durations"]) / len(b["talk_durations"]), 1)
                if b["talk_durations"] else None),
            # --- rate targets (demand-side, independent of batch scheduling) ---
            "connect_rate": _safe_rate(connected, attempted),
            "test_drive_interest_rate": _safe_rate(b["test_drive_interest_yes_count"], scored),
            "purchase_interest_rate": _safe_rate(b["purchase_interest_yes_count"], scored),
            # --- known-future covariates (doc §7.2) ---
            "hour_of_day": bucket_start.hour,
            "weekday": weekday,
            "is_business_hours": (business_hours_cfg["start_hour"] <= bucket_start.hour
                                   < business_hours_cfg["end_hour"]
                                   and weekday in business_hours_cfg["working_days"]),
            "active_campaign_count": len(b["campaign_ids"]),
            "feature_version": feature_version,
        })
    return rows
