"""
Response-Window Intelligence — SIMULATED DEMO VARIANT (2026-09-02).

The real card (response_window.py) uses the real test_drive_scheduled field, which has only
20 bookings across all 5,383 leads — too sparse for most buckets to show a meaningful rate.
That sparsity is a genuine fact about this pilot, not a gap to fill: padding the REAL count
with fabricated bookings would misrepresent an outcome we already know, unlike contact timing
(which is genuinely unknown pending real KIFS timestamps). Confirmed with the user before
building this — the fix is a fully separate, clearly-labeled comparison, never a blend.

This card answers "what would this breakdown look like with more volume" using
sales_intelligence_test_drive_booking_sim (apps.datastore.repositories
.test_drive_booking_sim_repo) — entirely fabricated bookings, correlated with real signals
(test_drive_interest_flag, purchase_interest_latest, nba_priority_latest) via
simulate_test_drive_bookings.py, seeded and tagged, never touching the real 20.

Contact timing here is STILL the same simulated sales_intelligence_outcome_sim as the real
card — so unlike that card, this one is simulated on BOTH axes. Never present this card's
numbers as evidence of anything about real customers.
"""
from apps.analytics.services.response_window import WINDOWS, _bucket
from apps.datastore.repositories import outcome_repo, test_drive_booking_sim_repo

CAVEAT = (
    "Both the contact timing and the booking volume on this card are preview data, built to "
    "show what this breakdown will look like once there's more booking volume to work with. "
    "The real card above, with its 20 actual bookings, remains the authoritative count -- this "
    "comparison view should not be quoted in its place."
)


def compute() -> dict:
    booked = test_drive_booking_sim_repo.booked_by_call_decision()
    outcomes = outcome_repo.all_rows()
    total_nba_suggested = len(outcomes)

    groups: dict[str, dict] = {label: {"n": 0, "td_booked": 0} for label, *_ in WINDOWS}
    groups["Never contacted"] = {"n": 0, "td_booked": 0}
    unmatched = 0

    for row in outcomes:
        cid = row.get("source_call_decision_id")
        if cid not in booked:
            unmatched += 1
            continue
        mins = row.get("nba_to_contact_mins")
        bucket = _bucket(mins) if mins is not None else "Never contacted"
        g = groups[bucket]
        g["n"] += 1
        if booked[cid]:
            g["td_booked"] += 1

    order = [w[0] for w in WINDOWS] + ["Never contacted"]
    total_booked = sum(g["td_booked"] for g in groups.values())
    breakdown = []
    for label in order:
        g = groups[label]
        breakdown.append({
            "window": label,
            "n": g["n"],
            "pct_of_all_nba": round(100 * g["n"] / total_nba_suggested, 1) if total_nba_suggested else None,
            "test_drive_booked": g["td_booked"],
            "test_drive_booked_pct": round(100 * g["td_booked"] / g["n"], 1) if g["n"] else None,
        })

    return {
        "provenance": "SIMULATED",
        "caveat": CAVEAT,
        "breakdown": breakdown,
        "total_nba_suggested": total_nba_suggested,
        "total_test_drives_booked": total_booked,
        "unmatched_rows": unmatched,
        "sim_seed": 20260902,
    }
