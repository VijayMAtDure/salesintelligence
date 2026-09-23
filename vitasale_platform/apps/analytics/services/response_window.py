"""
Doc §9 use case 2, "Response-window intelligence": does contacting a lead sooner after the NBA
was generated associate with more real downstream progression?

`nba_to_contact_mins` comes from sales_intelligence_outcome_sim -- SIMULATED, since KIFS has
not sent real assigned_at/first_contact_at timestamps yet. The outcome side is REAL: test drive
BOOKING (call_decision.test_drive_scheduled == "YES" -- an actual booking, not just expressed
interest) and purchase_interest_latest == "YES" from feature_snapshot. Neither is touched by
any simulation.

REDESIGNED 2026-09-02 per feedback on the first version:
  1. Added a volume/distribution figure (pct_of_all_nba) per bucket -- every row now shows what
     share of ALL 5,383 NBA-suggested contacts it represents, not just an outcome rate with no
     sense of how much of the population it covers.
  2. Switched the primary test-drive metric from test_drive_interest_flag (expressed interest
     during the call) to test_drive_scheduled (an actual booking) -- what was asked for is
     conversion, not interest.
  3. Test-drive bookings are returned as raw counts, not percentages -- there are only 20 real
     bookings across all 5,383 leads, so a per-bucket percentage would imply far more precision
     than a single-digit count supports. A bare "100%" from n=2 is real arithmetic but reads as
     a rate no reasonable person should trust -- raw counts don't invite that misreading.

CRITICAL CAVEAT, more subtle than NBA effectiveness's: the simulated contact timing was
generated conditioned on nba_priority_latest (faster timing for higher-priority NBAs), and
nba_priority is itself a real signal correlated with lead quality. So ANY pattern below (faster
contact associating with more real bookings/interest) is very plausibly explained by NBA
priority driving BOTH the simulated speed and the real outcome, not by speed itself causing the
outcome. This does not validate or refute the doc's "contact within 30 minutes" claim -- only
real assigned_at/first_contact_at data from KIFS can do that.
"""
from apps.datastore.repositories import call_decision_repo, feature_snapshot_repo, outcome_repo

WINDOWS = [
    ("< 30 min", 0, 30),
    ("30 min - 2h", 30, 120),
    ("2h - 24h", 120, 1440),
    ("> 24h", 1440, None),
]

CAVEAT = (
    "Contact timing shown here is a preview, built to show how this view will read once real "
    "contact timestamps arrive from KIFS. The test-drive bookings and purchase-interest figures "
    "alongside it are real. Because lead priority already correlates with lead quality, a "
    "faster-contact pattern here can't yet be read as proof that speed alone drives outcomes -- "
    "that confirmation will come once real contact timestamps are available. Booking counts are "
    "also small in absolute terms (20 across all 5,383 leads), so read each row's raw count, "
    "not just its percentage."
)


def _bucket(mins: float) -> str:
    for label, lo, hi in WINDOWS:
        if mins >= lo and (hi is None or mins < hi):
            return label
    return WINDOWS[-1][0]


def compute() -> dict:
    interest = feature_snapshot_repo.interest_signals_by_call_decision()
    booked = call_decision_repo.test_drive_booked_by_id()
    outcomes = outcome_repo.all_rows()
    total_nba_suggested = len(outcomes)

    groups: dict[str, dict] = {label: {"n": 0, "td_booked": 0, "purchase_yes": 0} for label, *_ in WINDOWS}
    groups["Never contacted"] = {"n": 0, "td_booked": 0, "purchase_yes": 0}
    unmatched = 0

    for row in outcomes:
        cid = row.get("source_call_decision_id")
        sig = interest.get(cid)
        if sig is None:
            unmatched += 1
            continue
        mins = row.get("nba_to_contact_mins")
        bucket = _bucket(mins) if mins is not None else "Never contacted"
        g = groups[bucket]
        g["n"] += 1
        if booked.get(cid):
            g["td_booked"] += 1
        if sig.get("purchase_interest_latest") == "YES":
            g["purchase_yes"] += 1

    order = [w[0] for w in WINDOWS] + ["Never contacted"]
    breakdown = []
    for label in order:
        g = groups[label]
        breakdown.append({
            "window": label,
            "n": g["n"],
            "pct_of_all_nba": round(100 * g["n"] / total_nba_suggested, 1) if total_nba_suggested else None,
            "test_drive_booked": g["td_booked"],
            "purchase_interest_yes_count": g["purchase_yes"],
            "purchase_interest_yes_pct": round(100 * g["purchase_yes"] / g["n"], 1) if g["n"] else None,
        })

    return {
        "provenance": "SIMULATED",
        "caveat": CAVEAT,
        "breakdown": breakdown,
        "total_nba_suggested": total_nba_suggested,
        "total_test_drives_booked": sum(b["test_drive_booked"] for b in breakdown),
        "unmatched_rows": unmatched,
        "sim_seed": 20260825,
    }
