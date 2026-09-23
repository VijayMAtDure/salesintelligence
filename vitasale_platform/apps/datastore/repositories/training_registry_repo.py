"""
Read/write access to sales_intelligence_model_run + sales_intelligence_prediction — the
SurrealDB side of the model registry (doc §13/§14 contract). The Django-side ModelVersion
row (apps.training.models) is the control-plane record of a training run; THIS is where the
actual leaderboard/prediction data it points to lives, matching the split from architecture
doc §2.

Field-kind maps and the general write path (INSERT/UPSERT) are ported unchanged from
persist_predictions.py / load.py — same tables, same schema.
"""
from apps.datastore.surql_writer import bulk_insert, to_surql
from apps.datastore.surreal_client import get_client

RUN_KINDS = {"trained_at": "datetime"}
PRED_KINDS = {
    "organisation": "record", "showroom_id": "record", "product_id": "record",
    "forecast_at": "datetime", "target_timestamp": "datetime",
}


def list_model_runs(track: str | None = None, target: str | None = None) -> list[dict]:
    db = get_client()
    clauses = []
    if track:
        clauses.append(f"track = '{track}'")
    if target:
        clauses.append(f"target = '{target}'")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return db.select(f"SELECT * FROM sales_intelligence_model_run {where};")


def get_predictions(model_run_id: str) -> list[dict]:
    db = get_client()
    return db.select(
        f"SELECT * FROM sales_intelligence_prediction WHERE model_run_id = '{model_run_id}';"
    )


def write_model_run(run: dict) -> int:
    """One row. `run` must already match the sales_intelligence_model_run schema — building
    that dict is the training service's job (apps/training/services/), this repository only
    persists it."""
    db = get_client()
    return bulk_insert(db, "sales_intelligence_model_run", [run], RUN_KINDS)


def write_predictions(predictions: list[dict]) -> int:
    db = get_client()
    return bulk_insert(db, "sales_intelligence_prediction", predictions, PRED_KINDS, batch_size=200)


def delete_predictions_for_run(model_run_id: str) -> None:
    """Used when re-persisting a corrected/rerun result for the same model_run_id — avoids
    duplicate prediction rows rather than relying on upsert semantics here."""
    db = get_client()
    db.query(f"DELETE sales_intelligence_prediction WHERE model_run_id = {to_surql(model_run_id)};")
