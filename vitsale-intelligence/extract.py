"""
Stage 1 — Extraction. Pulls raw rows from source tables, applies filters, normalizes
timestamps. Nothing computed here — see PHASE1_PHASE2_EXECUTION_FLOW.md Stage 1 for the
full source-table -> fields -> filter -> timezone-note matrix this module implements.

Backfill: no date bound (all matching rows). Incremental: callers pass since=<watermark>
to bound call_decision (and its joined rows) to `processed_at > since`.
"""
from db import SurrealDB
from timeutil import parse_naive_ist, parse_utc  # noqa: F401  (used once queries are filled in)

PILOT_START = "2026-07-31T00:00:00Z"  # reference doc §2 — conversation/message legacy cutoff


def extract_call_decisions(db: SurrealDB, since: str | None = None) -> list[dict]:
    """All 43 fields (design plan §9). since=<processed_at watermark> for incremental mode."""
    where = f"WHERE processed_at > '{since}'" if since else ""
    return db.select(f"SELECT * FROM call_decision {where} ORDER BY processed_at ASC;")


def extract_call_responses(db: SurrealDB) -> list[dict]:
    """createdDate is naive IST — normalize with timeutil.parse_naive_ist before use."""
    return db.select("SELECT * FROM call_response;")


def extract_campaign_call_log(db: SurrealDB) -> list[dict]:
    """Full dial history incl. NO_ANSWER — never reaches call_decision."""
    return db.select("SELECT * FROM campaign_call_log;")


def extract_campaign_call_retry(db: SurrealDB) -> list[dict]:
    return db.select("SELECT * FROM campaign_call_retry;")


def extract_campaign_followup(db: SurrealDB) -> list[dict]:
    return db.select("SELECT * FROM campaign_followup;")


def extract_scheduled_events(db: SurrealDB) -> list[dict]:
    """Only RETRY/FOLLOWUP event_types are relevant (reference doc §2A)."""
    return db.select(
        "SELECT * FROM scheduled_event WHERE event_type IN ['RETRY', 'FOLLOWUP'];"
    )


def extract_leads(db: SurrealDB) -> list[dict]:
    """Identity fields only. NEVER pull created_at for tenure math — legacy CRM date
    for 99% of rows, not pilot-relevant (reference doc §2)."""
    return db.select(
        "SELECT id, name, phone, city, product_interest, organisation FROM lead;"
    )


def extract_live_messages(db: SurrealDB) -> list[dict]:
    """Mandatory filter via the PARENT CONVERSATION's created_at, not message.created_at
    directly — message.created_at is stamped at migration-insert time uniformly for legacy
    rows too (confirmed 2026-08-20: filtering on message.created_at directly returned
    23,271 rows instead of the validated 214). conversation.created_at correctly preserves
    the original/business date. 99.3% of this table is legacy migrated CRM data
    (reference doc §2) — never query message/conversation unfiltered."""
    return db.select(
        f"SELECT * FROM message WHERE conversation.created_at >= d'{PILOT_START}';"
    )


def extract_live_conversations(db: SurrealDB) -> list[dict]:
    return db.select(
        f"SELECT * FROM conversation WHERE created_at >= d'{PILOT_START}';"
    )


def extract_campaigns(db: SurrealDB) -> list[dict]:
    return db.select("SELECT * FROM campaign;")


def extract_product_catalog(db: SurrealDB) -> list[dict]:
    """Stage 1B reference data — backfilled 2026-08-20."""
    return db.select("SELECT * FROM master_product_price_list;")


def extract_call_turns(db: SurrealDB) -> list[dict]:
    """Turn-level voice data (Stage 2c, from the ElevenLabs backfill). Unlocks the doc §6
    Engagement family (conversation_duration, customer:agent ratio, engagement depth,
    re-engagement) and the Latency family's AI_processing_time — none of which were
    buildable before this table existed."""
    return db.select(
        "SELECT call_response_id, role, interrupted, time_in_call_secs, "
        "llm_ttfb_secs, tts_ttfb_secs, silence_before_secs, message "
        "FROM sales_intelligence_call_turn;"
    )


def extract_meta_leads(db: SurrealDB) -> list[dict]:
    """Hyperlocal (Meta/Facebook/Instagram Lead Ads) pre-call metadata -- see
    hyperlocal/HYPERLOCAL_META_LEAD_INTEGRATION.md for the full field spec. One row per lead
    that came in through this channel; most leads won't have one at all (left/right join,
    not every lead is Meta-sourced) -- callers key this by lead_id and .get() it, never assume
    a match exists."""
    return db.select("SELECT * FROM sales_intelligence_meta_lead;")


def extract_showroom(db: SurrealDB) -> dict:
    """Single showroom in this pilot — backfilled 2026-08-20."""
    rows = db.select("SELECT * FROM showroom;")
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly 1 showroom, found {len(rows)}")
    return rows[0]
