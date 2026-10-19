"""
Timestamp normalization helpers. See PHASE1_DATA_AND_LOGIC_REFERENCE.md §6 item 7:
call_response.createdDate is a naive IST string (no timezone suffix); most other
datetime fields are proper UTC ISO strings. Never assume a uniform format across a table.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser

from db import load_config

_cfg = load_config()
BUSINESS_TZ = ZoneInfo(_cfg["timezone"]["business_tz"])
UTC = ZoneInfo("UTC")


def parse_iso(value: str) -> datetime:
    """SurrealDB returns nanosecond-precision fractional seconds (9 digits) —
    datetime.fromisoformat only supports up to 6 (Python <3.11). Use dateutil instead,
    which handles arbitrary precision correctly (confirmed 2026-08-20)."""
    return dateutil_parser.isoparse(value)


def parse_naive_ist(value: str) -> datetime:
    """For fields like call_response.createdDate: naive local (IST) string, no offset.
    Localizes to business_tz, returns UTC-aware datetime."""
    dt = parse_iso(value)
    if dt.tzinfo is not None:
        raise ValueError(f"expected a naive datetime string, got tz-aware: {value}")
    return dt.replace(tzinfo=BUSINESS_TZ).astimezone(UTC)


def parse_utc(value: str) -> datetime:
    """For fields already carrying a 'Z'/offset suffix (the common case)."""
    dt = parse_iso(value)
    if dt.tzinfo is None:
        raise ValueError(f"expected a tz-aware datetime string, got naive: {value}")
    return dt.astimezone(UTC)


def parse_flexible(value: str) -> datetime:
    """Handles both cases without the caller needing to know which one a given field is:
    naive strings are assumed IST (the LLM's date-output convention, per the Post Call
    Agent prompt — reference doc §3) and localized; tz-aware strings are used as-is.
    Confirmed 2026-08-20: NOT limited to call_response.createdDate — 360/3804
    call_decision.processed_at values are also naive, same convention. Always returns a
    UTC-aware datetime; callers should re-serialize with .isoformat() for consistent storage."""
    dt = parse_iso(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BUSINESS_TZ).astimezone(UTC)
    return dt.astimezone(UTC)
