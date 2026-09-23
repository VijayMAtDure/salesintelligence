"""
Read access to sales_intelligence_outcome_sim — the SIMULATED assignment/contact/outcome
timing chain built earlier this session to unblock NBA-effectiveness-shaped analysis before
KIFS sends real outcome data (assigned_at / first_contact_at / final_outcome). One row per
real lead (5,383), each explicitly tagged is_simulated=true, sim_version, sim_seed=20260825 —
see apps.analytics.services.nba_effectiveness for the caveat this data requires on every use.

When a real `sales_intelligence_outcome` table exists (KIFS export loaded), swapping to it is
a change to this repository's table name only — the join shape (source_call_decision_id) was
deliberately kept identical for exactly this reason.
"""
from apps.datastore.surreal_client import get_client

TABLE = "sales_intelligence_outcome_sim"
IS_SIMULATED = True  # flip when TABLE points at a real table


def all_rows() -> list[dict]:
    db = get_client()
    return db.select(f"SELECT * FROM {TABLE};")


def count() -> int:
    db = get_client()
    rows = db.select(f"SELECT count() FROM {TABLE} GROUP ALL;")
    return rows[0]["count"] if rows else 0
