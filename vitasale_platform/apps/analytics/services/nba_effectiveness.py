"""
Doc §9 use case 5, "NBA effectiveness": compare downstream progression of leads where the
recommended action was acted on versus not, grouped by how urgently it was recommended
(nba_priority_latest: IMMEDIATE / WITHIN_48_HOURS / SCHEDULED / NO_ACTION).

Runs against sales_intelligence_outcome_sim (apps.datastore.repositories.outcome_repo) —
SIMULATED assignment/contact/outcome timing, since KIFS has not yet sent real
assigned_at/first_contact_at/final_outcome data. The generator (simulate_outcomes.py) makes a
"faster response -> better outcome" pattern true BY CONSTRUCTION, conditioned on
nba_priority_latest. That means any gradient this function finds proves the analysis pipeline
correctly detects the pattern it was designed to produce -- it is NOT evidence that NBAs work
on real customers. This caveat is returned in the payload itself, not left to documentation,
so it can never be silently dropped by a UI that forgets to read a separate doc.
"""
from apps.datastore.repositories import feature_snapshot_repo, outcome_repo

PRIORITY_ORDER = ["IMMEDIATE", "WITHIN_48_HOURS", "SCHEDULED", "NO_ACTION"]

CAVEAT = (
    "This view uses preview response-and-outcome timing, built to show how this analysis will "
    "read once real timestamps are available from KIFS. It correctly shows a faster-response-"
    "to-better-outcome pattern because that pattern was built into the preview data by design -- "
    "it is not yet evidence that faster follow-up drives better real-world results. It will "
    "update automatically to real customer timing the moment KIFS sends it, with no other "
    "changes needed."
)


def compute() -> dict:
    priorities = feature_snapshot_repo.nba_priority_by_call_decision()
    outcomes = outcome_repo.all_rows()

    groups: dict[str, dict] = {p: {"total": 0, "acted_on": 0} for p in PRIORITY_ORDER}
    unmatched = 0
    for row in outcomes:
        priority = priorities.get(row.get("source_call_decision_id"))
        if priority not in groups:
            unmatched += 1
            continue
        groups[priority]["total"] += 1
        if row.get("final_outcome") != "never_contacted":
            groups[priority]["acted_on"] += 1

    breakdown = []
    for p in PRIORITY_ORDER:
        g = groups[p]
        rate = round(100 * g["acted_on"] / g["total"], 1) if g["total"] else None
        breakdown.append({
            "priority": p, "n": g["total"], "acted_on": g["acted_on"], "acted_on_pct": rate,
        })

    return {
        "provenance": "SIMULATED",
        "caveat": CAVEAT,
        "breakdown": breakdown,
        "total_outcome_rows": len(outcomes),
        "total_feature_rows": len(priorities),
        "unmatched_rows": unmatched,
        "sim_seed": 20260825,
    }
