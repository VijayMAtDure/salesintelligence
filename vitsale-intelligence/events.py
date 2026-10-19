"""
Stage 2 — Canonical Event Normalization -> sales_intelligence_call_event.
Maps each extracted row to one canonical event row per PHASE1_PHASE2_EXECUTION_FLOW.md
Stage 2's event_type table. event_id is a deterministic hash of
(source_table, source_id, event_type) so upserts are idempotent (doc §12.2).

payload carries the full raw source row for traceability (doc §12.2 "record source event
IDs used to construct derived features where practical") and so features.py never has to
re-query — everything walk_lead() needs is already on the event.
"""
import hashlib

from timeutil import parse_flexible


def make_event_id(source_table: str, source_id: str, event_type: str) -> str:
    return hashlib.sha1(f"{source_table}:{source_id}:{event_type}".encode()).hexdigest()[:20]


def _record_str(v):
    """SurrealDB record links come back as e.g. lead:abc123 or a RecordID object
    depending on client — normalize to the 'table:id' string form used as lead_id
    throughout this pipeline."""
    return str(v) if v is not None else None


def _looks_like_iso_datetime(v) -> bool:
    return isinstance(v, str) and len(v) >= 4 and v[:4].isdigit()


def _best_timestamp(row: dict, *field_names: str) -> str:
    """Returns the first field value that looks like a real ISO datetime string.
    Confirmed 2026-08-20: call_decision.processed_at is NONE on 2/3804 rows and the
    literal garbage string 'not_mentioned' (upstream data-quality bug, not ours to fix
    here) on 15/3804 rows — both must fall through to updatedDate/createdDate."""
    for name in field_names:
        val = row.get(name)
        if _looks_like_iso_datetime(val):
            return val
    raise ValueError(f"no valid timestamp found in fields {field_names} on row {row.get('id')}")


def build_events(call_decisions, call_responses, campaign_call_log, campaign_followups,
                  scheduled_events, messages, conversations_by_id, feature_version,
                  organisation: str) -> list[dict]:
    """organisation: the pilot's single-tenant constant (config.yaml pilot.organisation).
    Per-row organisationId/organisation fields are NOT trusted (confirmed 2026-08-20:
    2/3804 call_response rows carry a mislabeled organisationId) — every event in this
    single-tenant pipeline uses the known-correct constant instead."""
    events = []

    call_response_by_id = {_record_str(r["id"]): r for r in call_responses}

    # CALL_ATTEMPTED — every dial attempt, including NO_ANSWER
    for row in campaign_call_log:
        events.append({
            "event_id": make_event_id("campaign_call_log", _record_str(row["id"]), "CALL_ATTEMPTED"),
            "lead_id": row["lead_id"],
            "organisation": organisation,
            "campaign_id": _record_str(row.get("campaign_id")),
            "event_type": "CALL_ATTEMPTED",
            "event_timestamp": row["created_at"],
            "actor": "SYSTEM",
            "channel": "VOICE",
            "source_table": "campaign_call_log",
            "source_id": _record_str(row["id"]),
            "parent_event_id": None,
            "payload": row,
            "feature_version": feature_version,
        })

    # CALL_CONNECTED — only where the customer actually connected
    for row in call_responses:
        if not row.get("customerConnected"):
            continue
        events.append({
            "event_id": make_event_id("call_response", _record_str(row["id"]), "CALL_CONNECTED"),
            "lead_id": row["leadId"],
            "organisation": organisation,
            "campaign_id": row.get("campaignId"),
            "event_type": "CALL_CONNECTED",
            "event_timestamp": row["callStartTime"],
            "actor": "CUSTOMER",
            "channel": "VOICE",
            "source_table": "call_response",
            "source_id": _record_str(row["id"]),
            "parent_event_id": None,
            "payload": row,
            "feature_version": feature_version,
        })

    # CALL_DECISION_SCORED — the core signal, joined to call_response for lead_id
    for row in call_decisions:
        cr_id = row.get("callResponseId")
        cr = call_response_by_id.get(cr_id)
        if cr is None:
            # call_decision with no matching call_response — shouldn't happen (1:1 by
            # construction, reference doc §5) but don't silently drop; skip with a note
            # for validation.py to surface later.
            continue
        parent_id = make_event_id("call_response", cr_id, "CALL_CONNECTED")
        event_ts = _best_timestamp(row, "processed_at", "updatedDate", "createdDate")
        events.append({
            "event_id": make_event_id("call_decision", _record_str(row["id"]), "CALL_DECISION_SCORED"),
            "lead_id": cr["leadId"],
            "organisation": organisation,
            "campaign_id": row.get("campaign_id"),
            "event_type": "CALL_DECISION_SCORED",
            "event_timestamp": event_ts,
            "actor": "VITASALE",
            "channel": "VOICE",
            "source_table": "call_decision",
            "source_id": _record_str(row["id"]),
            "parent_event_id": parent_id,
            "payload": row,
            "feature_version": feature_version,
        })

    # FOLLOWUP_SCHEDULED / FOLLOWUP_EXECUTED
    for row in campaign_followups:
        rid = _record_str(row["id"])
        scheduled_event_id = make_event_id("campaign_followup", rid, "FOLLOWUP_SCHEDULED")
        if row.get("scheduled_at"):
            events.append({
                "event_id": scheduled_event_id,
                "lead_id": row["lead_id"],
                "organisation": organisation,
                "campaign_id": row.get("campaign_id"),
                "event_type": "FOLLOWUP_SCHEDULED",
                # event_timestamp is WHEN THE SCHEDULING DECISION HAPPENED, not the future
                # target time (row["scheduled_at"]). Confirmed 2026-08-26: using scheduled_at
                # padded the hourly forecast series with future-dated buckets from pending
                # (not-yet-executed) followups, which sat exactly in AutoGluon's validation
                # window and deflated every MASE toward zero — an artifact, not a real skill
                # improvement. scheduled_at is preserved in payload for anyone who needs the
                # target time; only the bucketing timestamp changes.
                "event_timestamp": row.get("created_at") or row["scheduled_at"],
                "actor": "SYSTEM",
                "channel": "VOICE",
                "source_table": "campaign_followup",
                "source_id": rid,
                "parent_event_id": None,
                "payload": row,
                "feature_version": feature_version,
            })
        if row.get("fired_at"):
            events.append({
                "event_id": make_event_id("campaign_followup", rid, "FOLLOWUP_EXECUTED"),
                "lead_id": row["lead_id"],
                "organisation": organisation,
                "campaign_id": row.get("campaign_id"),
                "event_type": "FOLLOWUP_EXECUTED",
                "event_timestamp": row["fired_at"],
                "actor": "SYSTEM",
                "channel": "VOICE",
                "source_table": "campaign_followup",
                "source_id": rid,
                "parent_event_id": scheduled_event_id,
                "payload": row,
                "feature_version": feature_version,
            })

    # RETRY_SCHEDULED / RETRY_EXECUTED
    for row in scheduled_events:
        rid = _record_str(row["id"])
        scheduled_event_id = make_event_id("scheduled_event", rid, "RETRY_SCHEDULED")
        payload = row.get("payload") or {}
        events.append({
            "event_id": scheduled_event_id,
            "lead_id": _record_str(row["lead_id"]),
            "organisation": organisation,
            "campaign_id": payload.get("campaignId"),
            "event_type": "RETRY_SCHEDULED",
            # same fix as FOLLOWUP_SCHEDULED above — created_at (real, already-happened) not
            # scheduled_at (future target time; pending retries were padding the series).
            "event_timestamp": row.get("created_at") or row["scheduled_at"],
            "actor": "SYSTEM",
            "channel": "VOICE",
            "source_table": "scheduled_event",
            "source_id": rid,
            "parent_event_id": None,
            "payload": row,
            "feature_version": feature_version,
        })
        if row.get("status") == "COMPLETED" and row.get("last_fired_at"):
            events.append({
                "event_id": make_event_id("scheduled_event", rid, "RETRY_EXECUTED"),
                "lead_id": _record_str(row["lead_id"]),
                "organisation": organisation,
                "campaign_id": payload.get("campaignId"),
                "event_type": "RETRY_EXECUTED",
                "event_timestamp": row["last_fired_at"],
                "actor": "SYSTEM",
                "channel": "VOICE",
                "source_table": "scheduled_event",
                "source_id": rid,
                "parent_event_id": scheduled_event_id,
                "payload": row,
                "feature_version": feature_version,
            })

    # CUSTOMER_MESSAGE / AGENT_MESSAGE — live slice only (already filtered in extract.py)
    for row in messages:
        conv_id = _record_str(row.get("conversation"))
        conv = conversations_by_id.get(conv_id)
        if conv is None:
            continue
        sender = row.get("sender")
        if sender == "CUSTOMER":
            event_type, actor = "CUSTOMER_MESSAGE", "CUSTOMER"
        elif sender == "AGENT":
            event_type, actor = "AGENT_MESSAGE", "VITASALE"
        else:
            continue  # BOT sender — not in the canonical event_type list, skip
        channel = _record_str(conv.get("channel")) or "channel:voice"
        events.append({
            "event_id": make_event_id("message", _record_str(row["id"]), event_type),
            "lead_id": _record_str(conv["lead"]),
            "organisation": organisation,
            "campaign_id": None,
            "event_type": event_type,
            "event_timestamp": row["created_at"],
            "actor": actor,
            "channel": "WHATSAPP" if "whatsapp" in channel else "VOICE",
            "source_table": "message",
            "source_id": _record_str(row["id"]),
            "parent_event_id": None,
            "payload": row,
            "feature_version": feature_version,
        })

    # Normalize every event_timestamp through the same flexible parser in one pass —
    # confirmed 2026-08-20: naive-IST timestamps appear on call_response.createdDate AND
    # call_response.callStartTime AND 360/3804 call_decision.processed_at values. Rather
    # than special-case each source field, normalize once here so every event this
    # pipeline ever produces carries a consistently tz-aware UTC event_timestamp.
    for ev in events:
        ev["event_timestamp"] = parse_flexible(ev["event_timestamp"]).isoformat()

    return events
