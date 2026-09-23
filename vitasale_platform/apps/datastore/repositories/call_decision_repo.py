"""
Read access to call_decision — the real, scored NBA record (5,383 rows). Used here for
test_drive_scheduled, a REAL field (not simulated) recording whether a test drive was actually
booked, as distinct from feature_snapshot's test_drive_interest_flag which only records
expressed interest during the call.
"""
from apps.datastore.surreal_client import get_client


def test_drive_booked_by_id() -> dict[str, bool]:
    db = get_client()
    rows = db.select("SELECT id, test_drive_scheduled FROM call_decision;")
    return {str(r["id"]): r.get("test_drive_scheduled") == "YES" for r in rows}


def purchase_timeline_by_id() -> dict[str, str | None]:
    """The real, general (non-hyperlocal) analog to the Meta form's buying_timeline -- stated
    urgency captured DURING the call itself, not pre-call. Confirmed live 2026-09-18: real and
    populated (IMMEDIATE/NEAR_TERM/LONG_TERM/NOT_MENTIONED), but sparse -- only 57 of 5,383
    rows have an actual stated timeline, the rest are the explicit NOT_MENTIONED value (not
    missing data, a real "wasn't discussed" outcome). Callers should treat NOT_MENTIONED as
    excluded from a breakdown, not as its own meaningful bucket."""
    db = get_client()
    rows = db.select("SELECT id, purchase_timeline FROM call_decision WHERE purchase_timeline != NONE;")
    return {str(r["id"]): r.get("purchase_timeline") for r in rows}
