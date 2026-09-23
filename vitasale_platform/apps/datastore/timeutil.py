"""
Timestamp normalization — ported from vitasale_intelligence/timeutil.py, unchanged logic.
Config source swapped from config.yaml to Django settings (BUSINESS_TZ_NAME), since Django
now owns configuration for the whole platform.

See PHASE1_DATA_AND_LOGIC_REFERENCE.md §6 item 7: some datetime fields (e.g.
call_response.createdDate) are naive IST strings with no timezone suffix; most others are
proper UTC ISO strings. Never assume a uniform format across a table — confirmed 2026-08-20
that this affects multiple fields, not just one.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser
from django.conf import settings

UTC = ZoneInfo("UTC")


def _business_tz() -> ZoneInfo:
    return ZoneInfo(settings.BUSINESS_TZ_NAME)


def parse_iso(value: str) -> datetime:
    """SurrealDB returns nanosecond-precision fractional seconds (9 digits) —
    datetime.fromisoformat only supports up to 6 (Python <3.11). dateutil handles arbitrary
    precision correctly (confirmed 2026-08-20)."""
    return dateutil_parser.isoparse(value)


def parse_naive_ist(value: str) -> datetime:
    """For fields like call_response.createdDate: naive local (IST) string, no offset.
    Localizes to the business timezone, returns UTC-aware."""
    dt = parse_iso(value)
    if dt.tzinfo is not None:
        raise ValueError(f"expected a naive datetime string, got tz-aware: {value}")
    return dt.replace(tzinfo=_business_tz()).astimezone(UTC)


def parse_utc(value: str) -> datetime:
    """For fields already carrying a 'Z'/offset suffix (the common case)."""
    dt = parse_iso(value)
    if dt.tzinfo is None:
        raise ValueError(f"expected a tz-aware datetime string, got naive: {value}")
    return dt.astimezone(UTC)


def parse_flexible(value: str) -> datetime:
    """Handles both cases without the caller needing to know which one a given field is:
    naive strings are assumed to be in the business timezone (the LLM's date-output
    convention, per the Post Call Agent prompt) and localized; tz-aware strings are used
    as-is. Confirmed 2026-08-20: not limited to one field — 360/3804 call_decision.processed_at
    values are also naive, same convention. Always returns UTC-aware."""
    dt = parse_iso(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_business_tz()).astimezone(UTC)
    return dt.astimezone(UTC)
