"""
Read access to sales_intelligence_test_drive_booking_sim — a SEPARATE, explicitly fabricated
demo comparison for the Response-Window Intelligence card (built 2026-09-02, confirmed with
the user first). Never confused with the real 20 bookings on call_decision.test_drive_scheduled
-- this table exists purely to answer "what would this look like with more volume," kept in
its own table so it can never accidentally get blended into a real count.
"""
from apps.datastore.surreal_client import get_client


def booked_by_call_decision() -> dict[str, bool]:
    db = get_client()
    rows = db.select(
        "SELECT source_call_decision_id, test_drive_booked_sim "
        "FROM sales_intelligence_test_drive_booking_sim;"
    )
    return {r["source_call_decision_id"]: bool(r.get("test_drive_booked_sim")) for r in rows}
