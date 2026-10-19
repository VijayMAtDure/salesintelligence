"""
Stage 3 + 4 — Per-lead chronological state walk -> sales_intelligence_feature_snapshot.
See PHASE1_PHASE2_EXECUTION_FLOW.md Stage 3 (algorithm) and Stage 4 (field -> source map,
revised 2026-08-20 after the doc §6.2 alignment check).

Key decisions baked into this module (do not relitigate without checking the docs):
  - Grain: one snapshot per CALL_DECISION_SCORED event, not hourly (design plan §1).
  - Sentiment encoding: POSITIVE=+1, NEUTRAL=0, NEGATIVE=-1, MIXED=0 (config.yaml).
  - purchase_interest ordinal encoding: NOT_MENTIONED=0, NO=0, MAYBE=1, YES=2.
  - No qualification_score proxy — field stays null (design plan §2C decision).
  - avg_dealer_response_minutes stays null — pending, source not yet identified.
  - product_id/showroom_id resolved via Stage 1B matching, not left null (revised 2026-08-20).
  - days_since_last_call / time_to_first_response computed relative to snapshot_at, NEVER
    "now" (leakage rule, doc §11).
"""
import re

from timeutil import parse_iso as _parse_dt

PURCHASE_INTEREST_ORDINAL = {"NOT_MENTIONED": 0, "NO": 0, "MAYBE": 1, "YES": 2}


def new_lead_state() -> dict:
    return {
        "calls_total": 0, "calls_connected": 0,
        "sentiment_history": [], "purchase_interest_history": [],
        "whatsapp_sent_count": 0,
        "followups_scheduled": 0, "followups_completed": 0,
        "followups_cancelled": 0, "followups_exhausted": 0,
        "retries_pending": 0,
        "first_attempt_at": None, "first_connected_at": None,
        "time_to_first_response_minutes": None,  # computed once, then frozen
        "last_decision_at": None,  # previous call_decision's snapshot_at, for days_since_last_call
        "competitor_mention_count": 0, "finance_interest_ever": False,
        "test_drive_interest_ever_yes": False, "escalate_flag": False, "assign_rep_flag": False,
        "messages_customer": 0, "messages_agent": 0,
        "disposition_history": [],
        "followup_latencies_minutes": [],  # for mean, per lead
        # --- added 2026-08-21, closing doc §6 feature-family gaps ---
        "last_customer_event_at": None,     # §6.2 last_customer_gap_minutes
        "momentum_score_prev": None,        # §10 momentum_change
        "channel_history": [],              # §6 Channel family
        "conversation_duration_total": 0,   # §6 Engagement family (from call_turn)
        "customer_turns_total": 0, "agent_turns_total": 0, "interruptions_total": 0,
        "ai_processing_times": [],          # §6 Latency: AI_processing_time
        "silences_before": [],              # §6 Engagement: dead air before agent turns
    }


def business_time_features(dt, business_hours_cfg, business_tz) -> dict:
    """doc §7.2 known-future covariates + §20 timezone mitigation. Evaluated in the
    organisation's business timezone, never UTC — an 09:30 IST call is in business hours
    even though it's 04:00 UTC.

    v1.2 adds cyclical encoding: raw hour_of_day tells a model that 23:00 and 00:00 are
    maximally distant, when they are adjacent. sin/cos encoding fixes that — standard
    practice for any periodic feature fed to a tree or linear model."""
    import math
    local = dt.astimezone(business_tz)
    weekday = local.weekday()
    in_hours = (business_hours_cfg["start_hour"] <= local.hour < business_hours_cfg["end_hour"]
                and weekday in business_hours_cfg["working_days"])
    return {
        "hour_of_day": local.hour,
        "weekday": weekday,
        "is_business_hours": in_hours,
        "is_weekend": weekday >= 5,
        "hour_sin": round(math.sin(2 * math.pi * local.hour / 24), 4),
        "hour_cos": round(math.cos(2 * math.pi * local.hour / 24), 4),
        "weekday_sin": round(math.sin(2 * math.pi * weekday / 7), 4),
        "weekday_cos": round(math.cos(2 * math.pi * weekday / 7), 4),
    }


# Mumbai metropolitan region + Goa = KIFS service area.
# ⚠️ PROVISIONAL. Our earlier keyword list was ~40% wrong (it classified Prabhadevi, Kurla,
# Vashi and Ambarnath as out-of-territory when all are Mumbai metro). This list is corrected
# for those cases but is still an inference — the authoritative KIFS service-area definition
# is an outstanding ask (see KIFS_DATA_REQUIREMENT.md §4).
IN_TERRITORY = {
    "mumbai", "bombay", "navi mumbai", "thane", "goa", "panaji", "panjim", "margao", "vasco",
    "andheri", "bandra", "borivali", "powai", "worli", "dadar", "juhu", "malad", "kandivali",
    "chembur", "ghatkopar", "mulund", "vashi", "belapur", "kurla", "prabhadevi", "parbhadevi",
    "santacruz", "khar", "colaba", "byculla", "sion", "matunga", "vile parle", "goregaon",
    "jogeshwari", "kanjurmarg", "bhandup", "vikhroli", "wadala", "lower parel", "mahim",
    "vasai", "virar", "panvel", "kalyan", "dombivli", "ambarnath", "ambernath", "badlapur",
    "mira road", "bhayandar", "ulhasnagar", "airoli", "nerul", "kharghar", "taloja",
}


def territory_status(city) -> str:
    """in_territory / out_of_territory / unknown.

    Not in doc §6, added v1.2 because the CRM outcome analysis showed territory is the
    variable that separates commercially useful leads from wasted ones — and engagement
    features cannot see it (out-of-territory leads were the MOST engaged group). A model
    trained without this would confidently rank unservable leads at the top."""
    if not city:
        return "unknown"
    c = str(city).strip().lower()
    if not c or c in ("not_mentioned", "none", "n/a"):
        return "unknown"
    return "in_territory" if any(t in c for t in IN_TERRITORY) else "out_of_territory"


def _safe_ratio(num, den, digits: int = 4):
    """Ratios are scale-invariant where raw counts are not: 5 interruptions across 40 turns
    is a very different conversation from 5 across 8. Returns None rather than 0 when the
    denominator is absent, so 'no data' stays distinguishable from 'genuinely zero'."""
    if not den:
        return None
    return round(num / den, digits)


def turn_features_for_call(turns: list[dict]) -> dict:
    """doc §6 Engagement family + AI_processing_time, from sales_intelligence_call_turn.
    These were previously unbuildable — call_response.transcript is a flat text blob with
    no turn structure (reference doc §2c). Engagement depth here is the empirically
    validated differentiator: interested leads average 38 turns / 281s / 5.4 interruptions
    vs 13 turns / 81s / 1.8 for connected-but-not-interested (see execution flow §Final
    prediction scope item 7)."""
    if not turns:
        return {"conversation_duration_secs": None, "customer_turns": 0, "agent_turns": 0,
                "total_turns": 0, "interruptions": 0, "customer_agent_ratio": None,
                "ai_processing_time_secs": None, "avg_silence_before_secs": None}
    customer_turns = sum(1 for t in turns if t["role"] == "CUSTOMER")
    agent_turns = sum(1 for t in turns if t["role"] == "AGENT")
    interruptions = sum(1 for t in turns if t.get("interrupted"))
    duration = max((t.get("time_in_call_secs") or 0) for t in turns)
    ai_times = [(t.get("llm_ttfb_secs") or 0) + (t.get("tts_ttfb_secs") or 0)
                for t in turns if t.get("llm_ttfb_secs") is not None]
    # Dead air before the agent starts a turn — a validated differentiator: interested
    # leads averaged 0.9s vs 1.4s for connected-but-not-interested (see execution flow
    # §Final prediction scope item 7). Lower = more fluid, responsive exchange.
    silences = [t["silence_before_secs"] for t in turns
                if t.get("silence_before_secs") is not None]
    return {
        "conversation_duration_secs": duration,
        "customer_turns": customer_turns,
        "agent_turns": agent_turns,
        "total_turns": len(turns),
        "interruptions": interruptions,
        "customer_agent_ratio": round(customer_turns / agent_turns, 3) if agent_turns else None,
        "ai_processing_time_secs": round(sum(ai_times) / len(ai_times), 3) if ai_times else None,
        "avg_silence_before_secs": round(sum(silences) / len(silences), 3) if silences else None,
    }


def sentiment_recovery(history: list[float]) -> bool:
    """doc §6 Sentiment family: 'negative-to-positive recovery'. True if the lead ever went
    negative and later recovered to positive."""
    seen_negative = False
    for v in history:
        if v < 0:
            seen_negative = True
        elif v > 0 and seen_negative:
            return True
    return False


def channel_features(channel_history: list[str]) -> dict:
    """doc §6 Channel family. In this pilot voice dominates by construction (call_decision
    is voice-only); multi-channel only appears where a lead also has live WhatsApp
    messages."""
    if not channel_history:
        return {"channel_dominant": None, "channel_first": None, "channel_last": None,
                "channel_switches": 0, "is_multi_channel": False}
    switches = sum(1 for a, b in zip(channel_history, channel_history[1:]) if a != b)
    return {
        "channel_dominant": max(set(channel_history), key=channel_history.count),
        "channel_first": channel_history[0],
        "channel_last": channel_history[-1],
        "channel_switches": switches,
        "is_multi_channel": len(set(channel_history)) > 1,
    }


def match_product(interested_vehicles: list[str], catalog_by_model: dict[str, dict]) -> str | None:
    """Fuzzy-match a free-text interested_vehicles entry against master_product_price_list.
    Strips a leading 'Volvo ' prefix (case-insensitive), then checks whether any catalog
    model code appears as a whole-word token in the remaining text (handles "XC90 B5 Ultra",
    "XC60 electric", etc). Returns the FIRST match's product_id, or None — unmatched free
    text (discontinued/unofficial model names, e.g. old XC40/S90 mentions — reference doc
    §1B) is expected, not an error."""
    if not interested_vehicles:
        return None
    for raw in interested_vehicles:
        text = re.sub(r"^\s*volvo\s+", "", raw, flags=re.IGNORECASE).upper()
        tokens = set(re.findall(r"[A-Z0-9]+", text))
        for model, row in catalog_by_model.items():
            if model.upper() in tokens:
                return row["id"]
    return None


def walk_lead(lead_id: str, events_for_lead: list[dict], catalog_by_model: dict[str, dict],
               showroom_id: str, sentiment_encoding: dict[str, int],
               feature_version: str, turns_by_call_response: dict | None = None,
               business_hours_cfg: dict | None = None, business_tz=None,
               meta_lead_by_lead_id: dict | None = None) -> list[dict]:
    """Chronological walk over one lead's events (Stage 3). Emits one snapshot dict per
    CALL_DECISION_SCORED event encountered, in order.

    meta_lead_by_lead_id: {lead_id: sales_intelligence_meta_lead row}, only present for leads
    that came in via the hyperlocal/Meta channel (see extract.extract_meta_leads) -- most leads
    won't have an entry, that's normal, not a data-quality problem."""
    state = new_lead_state()
    snapshots = []
    meta_lead = (meta_lead_by_lead_id or {}).get(lead_id)

    ordered = sorted(events_for_lead, key=lambda e: _parse_dt(e["event_timestamp"]))

    # index scheduled events by their own event_id so *_EXECUTED can find the matching
    # *_SCHEDULED timestamp via parent_event_id (built in events.py)
    by_id = {e["event_id"]: e for e in ordered}

    for ev in ordered:
        et = ev["event_type"]
        payload = ev["payload"]

        if et == "CALL_ATTEMPTED":
            state["calls_total"] += 1
            state["channel_history"].append(ev.get("channel") or "VOICE")
            if state["first_attempt_at"] is None:
                state["first_attempt_at"] = ev["event_timestamp"]

        elif et == "CALL_CONNECTED":
            state["calls_connected"] += 1
            state["last_customer_event_at"] = ev["event_timestamp"]  # customer picked up
            if state["first_connected_at"] is None:
                state["first_connected_at"] = ev["event_timestamp"]
                if state["first_attempt_at"] is not None:
                    delta = _parse_dt(state["first_connected_at"]) - _parse_dt(state["first_attempt_at"])
                    state["time_to_first_response_minutes"] = round(delta.total_seconds() / 60, 1)
            # roll up this call's turn-level engagement (doc §6 Engagement + Latency)
            if turns_by_call_response:
                tf = turn_features_for_call(turns_by_call_response.get(ev["source_id"], []))
                if tf["conversation_duration_secs"] is not None:
                    state["conversation_duration_total"] += tf["conversation_duration_secs"]
                state["customer_turns_total"] += tf["customer_turns"]
                state["agent_turns_total"] += tf["agent_turns"]
                state["interruptions_total"] += tf["interruptions"]
                if tf["ai_processing_time_secs"] is not None:
                    state["ai_processing_times"].append(tf["ai_processing_time_secs"])
                if tf["avg_silence_before_secs"] is not None:
                    state["silences_before"].append(tf["avg_silence_before_secs"])

        elif et == "FOLLOWUP_SCHEDULED":
            state["followups_scheduled"] += 1

        elif et == "FOLLOWUP_EXECUTED":
            status = payload.get("status")
            if status == "ANSWERED":
                state["followups_completed"] += 1
            elif status == "CANCELLED":
                state["followups_cancelled"] += 1
            elif status == "EXHAUSTED":
                state["followups_exhausted"] += 1
            parent = by_id.get(ev["parent_event_id"])
            if parent is not None:
                delta = _parse_dt(ev["event_timestamp"]) - _parse_dt(parent["event_timestamp"])
                state["followup_latencies_minutes"].append(delta.total_seconds() / 60)

        elif et == "RETRY_SCHEDULED":
            state["retries_pending"] += 1

        elif et == "RETRY_EXECUTED":
            state["retries_pending"] = max(0, state["retries_pending"] - 1)

        elif et == "CUSTOMER_MESSAGE":
            state["messages_customer"] += 1
            state["last_customer_event_at"] = ev["event_timestamp"]
            state["channel_history"].append(ev.get("channel") or "WHATSAPP")

        elif et == "AGENT_MESSAGE":
            state["messages_agent"] += 1
            state["channel_history"].append(ev.get("channel") or "WHATSAPP")

        elif et == "CALL_DECISION_SCORED":
            cd = payload  # full call_decision row

            sentiment_val = sentiment_encoding.get(cd.get("sentiment_overall"), 0)
            state["sentiment_history"].append(sentiment_val)
            pi_val = PURCHASE_INTEREST_ORDINAL.get(cd.get("purchase_interest"), 0)
            state["purchase_interest_history"].append(pi_val)
            state["disposition_history"].append(cd.get("disposition_tag"))

            if cd.get("test_drive_interest") == "YES":
                state["test_drive_interest_ever_yes"] = True
            ctx_tags = cd.get("customer_context_tags") or []
            if "OWNS_COMPETITOR" in ctx_tags:
                state["competitor_mention_count"] += 1
            if "FINANCE_INTEREST" in ctx_tags:
                state["finance_interest_ever"] = True
            if cd.get("escalate"):
                state["escalate_flag"] = True
            if cd.get("assign_rep"):
                state["assign_rep_flag"] = True
            if cd.get("whatsapp_should_send"):
                state["whatsapp_sent_count"] += 1

            n = len(state["sentiment_history"])
            sentiment_velocity = (
                state["sentiment_history"][-1] - state["sentiment_history"][-2]
                if n >= 2 else None
            )
            pi_n = len(state["purchase_interest_history"])
            purchase_interest_velocity = (
                state["purchase_interest_history"][-1] - state["purchase_interest_history"][-2]
                if pi_n >= 2 else None
            )

            snapshot_at = ev["event_timestamp"]
            snapshot_dt = _parse_dt(snapshot_at)

            # ⚠️ FIXED 2026-09-21: first_attempt_at was previously set ONLY inside the
            # CALL_ATTEMPTED branch above, which is built exclusively from campaign_call_log
            # (events.py) -- the VOICE dialer's attempt log. WhatsApp-channel leads (confirmed:
            # 134/136 real hyperlocal leads use channel:whatsapp) never produce a CALL_ATTEMPTED
            # event at all, so first_attempt_at stayed None forever for them, silently blanking
            # BOTH days_in_pipeline (a real PROPENSITY_FEATURES column, likely affecting every
            # WhatsApp-only lead, not just hyperlocal ones) and meta_to_first_contact_mins below.
            # Falling back to this CALL_DECISION_SCORED event's own timestamp on first use makes
            # first_attempt_at channel-agnostic ("earliest evidence we engaged this lead") while
            # leaving voice-channel behavior untouched -- CALL_ATTEMPTED (from campaign_call_log)
            # already fires chronologically before any CALL_DECISION_SCORED event for those leads.
            if state["first_attempt_at"] is None:
                state["first_attempt_at"] = ev["event_timestamp"]

            days_in_pipeline = None
            if state["first_attempt_at"] is not None:
                days_in_pipeline = round(
                    (snapshot_dt - _parse_dt(state["first_attempt_at"])).total_seconds() / 86400, 2)

            days_since_last_call = None
            if state["last_decision_at"] is not None:
                days_since_last_call = round(
                    (snapshot_dt - _parse_dt(state["last_decision_at"])).total_seconds() / 86400, 2)

            followup_latency_minutes = (
                round(sum(state["followup_latencies_minutes"]) / len(state["followup_latencies_minutes"]), 1)
                if state["followup_latencies_minutes"] else None
            )

            nba_completed = 1 if cd.get("whatsapp_should_send") else 0
            nba_overdue = 1 if (cd.get("nba_priority") == "SCHEDULED" and state["retries_pending"] > 0) else 0

            product_id = match_product(cd.get("interested_vehicles") or [], catalog_by_model)

            # Hyperlocal (Meta) pre-call signal, 2026-09-18: real (not simulated) response-
            # window timing for leads that came in through this channel. fb_created_time is
            # Meta's own form-submission timestamp (see hyperlocal/HYPERLOCAL_META_LEAD_
            # INTEGRATION.md) -- distinct from state["first_attempt_at"]'s existing
            # time_to_first_response_minutes, which measures OUR call attempt to THEIR pickup,
            # not lead-arrival to our first attempt. Computed fresh each snapshot from
            # first_attempt_at (not cached) so it's always correct regardless of which
            # snapshot in this lead's history is being built.
            meta_to_first_contact_mins = None
            if meta_lead is not None and state["first_attempt_at"] is not None:
                delta = _parse_dt(state["first_attempt_at"]) - _parse_dt(meta_lead["fb_created_time"])
                meta_to_first_contact_mins = round(delta.total_seconds() / 60, 1)

            last_customer_gap_minutes = None
            if state["last_customer_event_at"] is not None:
                last_customer_gap_minutes = round(
                    (snapshot_dt - _parse_dt(state["last_customer_event_at"])).total_seconds() / 60, 1)

            time_feats = (business_time_features(snapshot_dt, business_hours_cfg, business_tz)
                          if business_hours_cfg and business_tz
                          else {"hour_of_day": None, "weekday": None, "is_business_hours": None})
            chan_feats = channel_features(state["channel_history"])
            total_turns_so_far = state["customer_turns_total"] + state["agent_turns_total"]

            snapshots.append({
                **time_feats,
                **chan_feats,
                "last_customer_gap_minutes": last_customer_gap_minutes,
                "conversation_duration_secs": state["conversation_duration_total"] or None,
                "customer_turns": state["customer_turns_total"],
                "agent_turns": state["agent_turns_total"],
                "total_turns": total_turns_so_far,
                "interruptions": state["interruptions_total"],
                "customer_agent_ratio": (round(state["customer_turns_total"] / state["agent_turns_total"], 3)
                                          if state["agent_turns_total"] else None),
                "engagement_depth": total_turns_so_far,   # §6 'engagement depth' — validated differentiator
                "re_engagement_count": max(0, state["calls_connected"] - 1),
                "ai_processing_time_secs": (round(sum(state["ai_processing_times"]) / len(state["ai_processing_times"]), 3)
                                             if state["ai_processing_times"] else None),
                "avg_silence_before_secs": (round(sum(state["silences_before"]) / len(state["silences_before"]), 3)
                                             if state["silences_before"] else None),
                "sentiment_recovery": sentiment_recovery(state["sentiment_history"]),

                # --- v1.2 derived ratios (doc §6 families, scale-invariant forms) ---------
                # Raw counts hide intensity; ratios expose it. All computed from columns
                # already present — no new source data required.
                "connect_rate_lead": _safe_ratio(state["calls_connected"], state["calls_total"]),
                "followup_completion_rate": _safe_ratio(state["followups_completed"],
                                                         state["followups_scheduled"]),
                "interruption_rate": _safe_ratio(state["interruptions_total"], total_turns_so_far),
                "turns_per_minute": _safe_ratio(
                    total_turns_so_far,
                    (state["conversation_duration_total"] / 60) if state["conversation_duration_total"] else 0,
                    3),
                "calls_per_day_in_pipeline": _safe_ratio(
                    state["calls_total"], days_in_pipeline, 3) if days_in_pipeline else None,
                # doc §6 NBA family: completion rate. nba_generated is 1 per snapshot, so
                # this is cumulative-completed over cumulative-generated for the lead.
                "nba_completion_rate": _safe_ratio(state["whatsapp_sent_count"],
                                                    len(state["disposition_history"])),
                "territory_status": territory_status(cd.get("vehicle_city")),
                "lead_id": lead_id,
                "organisation": ev["organisation"],
                "campaign_id": ev.get("campaign_id"),
                "snapshot_at": snapshot_at,
                "bucket": "event",
                "source_call_decision_id": ev["source_id"],
                "parent_event_id": ev.get("parent_event_id"),
                "attempt_number": None,  # filled by caller from call_response if available
                "disposition_latest": cd.get("disposition_tag"),
                "disposition_history": list(state["disposition_history"]),
                "messages_customer": state["messages_customer"],
                "messages_agent": state["messages_agent"],
                "total_interactions": state["messages_customer"] + state["messages_agent"],
                "sentiment_latest": sentiment_val,
                "sentiment_velocity": sentiment_velocity,
                "sentiment_mean": round(sum(state["sentiment_history"]) / n, 3),
                "sentiment_min": min(state["sentiment_history"]),
                "sentiment_max": max(state["sentiment_history"]),
                "purchase_interest_latest": cd.get("purchase_interest"),
                "purchase_interest_velocity": purchase_interest_velocity,
                "test_drive_interest_flag": state["test_drive_interest_ever_yes"],
                "intent_tags_latest": cd.get("intent_tags") or [],
                "qualification_score": None,  # descoped
                "nba_generated": 1,
                "nba_completed": nba_completed,
                "nba_overdue": nba_overdue,
                "nba_priority_latest": cd.get("nba_priority"),
                "competitor_mentions": state["competitor_mention_count"],
                "finance_interest_ever": state["finance_interest_ever"],
                "escalate_flag": state["escalate_flag"],
                "assign_rep_flag": state["assign_rep_flag"],
                "whatsapp_sent_count": state["whatsapp_sent_count"],
                "followups_scheduled": state["followups_scheduled"],
                "followups_completed": state["followups_completed"],
                "followups_cancelled": state["followups_cancelled"],
                "followups_exhausted": state["followups_exhausted"],
                "followup_latency_minutes": followup_latency_minutes,
                "retries_pending": state["retries_pending"],
                "calls_total": state["calls_total"],
                "calls_connected": state["calls_connected"],
                "calls_no_response": state["calls_total"] - state["calls_connected"],
                "days_in_pipeline": days_in_pipeline,
                "pipeline_velocity": None,  # descoped
                "days_since_last_call": days_since_last_call,
                "time_to_first_response_minutes": state["time_to_first_response_minutes"],
                "avg_dealer_response_minutes": None,  # pending source
                "momentum_score": None,  # filled below
                "momentum_state": None,
                "momentum_change": None,
                "top_positive_signal": None,
                "top_negative_signal": None,
                "showroom_id": showroom_id,
                "product_id": product_id,
                "outcome": None,  # descoped
                "feature_version": feature_version,
                "meta_to_first_contact_mins": meta_to_first_contact_mins,
                "meta_car_interest": meta_lead.get("car_interest") if meta_lead else None,
                "meta_buying_timeline": meta_lead.get("buying_timeline") if meta_lead else None,
            })

            state["last_decision_at"] = snapshot_at

            momentum_state, momentum_score, top_pos, top_neg = compute_momentum(
                sentiment_velocity, purchase_interest_velocity, days_since_last_call,
                cd.get("disposition_tag"), state["retries_pending"] > 0,
                test_drive_flag=state["test_drive_interest_ever_yes"],
                competitor_owner=state["competitor_mention_count"] > 0,
                total_turns=total_turns_so_far or None,
            )
            snapshots[-1]["momentum_score"] = momentum_score
            snapshots[-1]["momentum_state"] = momentum_state
            snapshots[-1]["top_positive_signal"] = top_pos
            snapshots[-1]["top_negative_signal"] = top_neg
            # §10 momentum_change: delta vs this lead's previous snapshot (null on first)
            snapshots[-1]["momentum_change"] = (
                momentum_score - state["momentum_score_prev"]
                if state["momentum_score_prev"] is not None else None
            )
            state["momentum_score_prev"] = momentum_score

    return snapshots


def compute_momentum(sentiment_velocity, purchase_interest_velocity, days_since_last_call,
                      disposition_latest, has_pending_followup,
                      stalled_days_threshold: float = 14.0,
                      test_drive_flag: bool = False, competitor_owner: bool = False,
                      total_turns: int | None = None) -> tuple[str, int, str | None, str | None]:
    """Descriptive only, not predictive (doc §10). Thresholds not yet tuned — revisit
    during Stage 9 validation once real snapshot output exists to inspect.

    Returns (momentum_state, momentum_score 0-100, top_positive_signal, top_negative_signal)
    — the two signal fields added 2026-08-21 to complete doc §10's five required outputs
    (was returning only state+score). They are what make momentum *explainable* rather
    than just a number.
    """
    trending_up = (sentiment_velocity or 0) > 0 or (purchase_interest_velocity or 0) > 0
    trending_down = (sentiment_velocity or 0) < 0 or (purchase_interest_velocity or 0) < 0

    # rank candidate signals, strongest first — mirrors the validated differentiators
    positives = []
    if test_drive_flag:
        positives.append("test_drive_interest")
    if (purchase_interest_velocity or 0) > 0:
        positives.append("purchase_interest_rising")
    if (sentiment_velocity or 0) > 0:
        positives.append("sentiment_rising")
    if total_turns is not None and total_turns >= 25:
        positives.append("high_engagement_depth")
    if competitor_owner:
        positives.append("owns_competitor_vehicle")
    if disposition_latest == "CONNECTED_POSITIVE":
        positives.append("connected_positive")

    negatives = []
    if disposition_latest == "DO_NOT_CONTACT":
        negatives.append("do_not_contact")
    if disposition_latest == "NOT_INTERESTED":
        negatives.append("declared_not_interested")
    if (sentiment_velocity or 0) < 0:
        negatives.append("sentiment_falling")
    if (purchase_interest_velocity or 0) < 0:
        negatives.append("purchase_interest_falling")
    if days_since_last_call is not None and days_since_last_call > stalled_days_threshold:
        negatives.append("no_contact_over_threshold")
    if disposition_latest == "NO_RESPONSE":
        negatives.append("no_response")
    if total_turns is not None and 0 < total_turns <= 5:
        negatives.append("minimal_engagement")

    top_pos = positives[0] if positives else None
    top_neg = negatives[0] if negatives else None

    if days_since_last_call is not None and days_since_last_call > stalled_days_threshold \
            and not has_pending_followup:
        return "STALLED", 10, top_pos, top_neg or "no_contact_over_threshold"

    if disposition_latest == "CONNECTED_POSITIVE" and trending_up:
        return "HIGH", 80, top_pos, top_neg
    if trending_down:
        return "DECLINING", 30, top_pos, top_neg
    if disposition_latest in ("CONNECTED_POSITIVE", "CALL_BACK_LATER"):
        return "STABLE", 55, top_pos, top_neg
    return "STABLE", 40, top_pos, top_neg
