"""
Read access to sales_intelligence_feature_snapshot — the propensity track's training/
inference input (5,383 rows, feature_version 1.2, 92 fields as of this platform's
scaffolding — see FEATURE_DICTIONARY.md for the full field-by-field reference).
"""
from apps.datastore.surreal_client import get_client


def count(feature_version: str | None = None) -> int:
    db = get_client()
    where = f"WHERE feature_version = '{feature_version}'" if feature_version else ""
    rows = db.select(f"SELECT count() FROM sales_intelligence_feature_snapshot {where} GROUP ALL;")
    return rows[0]["count"] if rows else 0


def sample(limit: int = 20, feature_version: str | None = None) -> list[dict]:
    """For the UI's data-preview screen (architecture doc §5.1, screen 3)."""
    db = get_client()
    where = f"WHERE feature_version = '{feature_version}'" if feature_version else ""
    return db.select(
        f"SELECT * FROM sales_intelligence_feature_snapshot {where} LIMIT {int(limit)};"
    )


def get_by_call_decision(source_call_decision_id: str) -> dict | None:
    """For inference: look up a specific lead's latest snapshot by its call_decision id."""
    db = get_client()
    rows = db.select(
        "SELECT * FROM sales_intelligence_feature_snapshot "
        f"WHERE source_call_decision_id = '{source_call_decision_id}';"
    )
    return rows[0] if rows else None


def nba_priority_by_call_decision() -> dict[str, str]:
    """Just the two fields apps.analytics.services.nba_effectiveness needs to join against
    outcome_repo — avoids pulling all 92 fields for every row for an analysis that only uses
    one of them."""
    db = get_client()
    rows = db.select(
        "SELECT source_call_decision_id, nba_priority_latest FROM sales_intelligence_feature_snapshot;"
    )
    return {r["source_call_decision_id"]: r.get("nba_priority_latest") for r in rows}


def interest_signals_by_call_decision() -> dict[str, dict]:
    """REAL expressed-interest fields keyed by source_call_decision_id — used as the outcome
    side of apps.analytics.services.response_window, deliberately never touched by any
    simulation (only the contact-timing side of that analysis is simulated)."""
    db = get_client()
    rows = db.select(
        "SELECT source_call_decision_id, test_drive_interest_flag, purchase_interest_latest "
        "FROM sales_intelligence_feature_snapshot;"
    )
    return {
        r["source_call_decision_id"]: {
            "test_drive_interest_flag": r.get("test_drive_interest_flag"),
            "purchase_interest_latest": r.get("purchase_interest_latest"),
        }
        for r in rows
    }


def lead_outcome_rows() -> list[dict]:
    """Snapshots for apps.assistant.services.query_lead_outcomes -- only the fields it needs,
    not all 92, but UNFILTERED across the whole real lead base (5,383 rows), not just
    hyperlocal-sourced ones.

    ⚠️ FIXED 2026-09-18: this used to filter `WHERE meta_to_first_contact_mins != NONE`,
    scoping EVERY dimension to hyperlocal-only leads even for ones with nothing to do with
    hyperlocal (product, city, email) -- confirmed live that this made "which car models book
    test drives fastest" answer "no data" even though car model, call timing, and test-drive
    outcome are all real and populated for the whole lead base. The meta_* fields are still
    NONE for non-hyperlocal rows (expected, most leads aren't hyperlocal-sourced) -- callers
    filter per-dimension now (query_lead_outcomes.py's existing skip-on-None-for-THIS-dimension
    logic already handles this correctly), not once for the whole dataset up front."""
    db = get_client()
    return db.select(
        "SELECT source_call_decision_id, lead_id, product_id, meta_to_first_contact_mins, "
        "meta_car_interest, meta_buying_timeline, test_drive_interest_flag, "
        "time_to_first_response_minutes, purchase_interest_latest "
        "FROM sales_intelligence_feature_snapshot;"
    )


def all_for_training(feature_version: str) -> list[dict]:
    """Full export for a training run. Mirrors export_training_data.py's propensity export —
    same source table, same feature_version filter, called from a job instead of a script."""
    db = get_client()
    return db.select(
        f"SELECT * FROM sales_intelligence_feature_snapshot WHERE feature_version = '{feature_version}';"
    )
