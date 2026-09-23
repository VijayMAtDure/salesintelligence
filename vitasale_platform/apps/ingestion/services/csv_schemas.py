"""
Per-table CSV validation contracts. `call_decision` has ~50 raw fields in production (it's
the client's own schemaless table, not something we DEFINE'd), but the pipeline (events.py /
features.py) only actually reads a subset of them — see PHASE1_DATA_AND_LOGIC_REFERENCE.md /
FEATURE_DICTIONARY.md for the full field-by-field trace. Required here is deliberately scoped
to what the pipeline consumes, not the full raw shape: a CSV upload represents new source data
from an external system, not a database replica, and demanding all ~50 columns would make this
unusable for its actual purpose.

Extend TABLE_SCHEMAS with more tables as CSV upload needs grow — nothing else in the ingestion
app is specific to call_decision.
"""

CALL_DECISION_SCHEMA = {
    "required": [
        "phone_number", "processed_at", "disposition_tag",
    ],
    "optional": [
        "callResponseId", "contact_id", "campaign_id", "sentiment_overall",
        "purchase_interest", "test_drive_interest", "test_drive_scheduled",
        "nba_priority", "nba_summary", "interested_vehicles", "vehicle_city",
        "assign_rep", "escalate", "resale_intent", "purchase_timeline",
        "brands_evaluating", "current_vehicle_make", "current_vehicle_model",
        "selekt_interest", "whatsapp_should_send", "finance_interest",
    ],
}

TABLE_SCHEMAS = {
    "call_decision": CALL_DECISION_SCHEMA,
}


def validate_headers(target_table: str, headers: list[str]) -> list[str]:
    """Returns a list of error strings; empty list means valid. Checks required columns are
    present and no unrecognized columns sneak in unnoticed (misspelled column names are a
    silent-corruption risk otherwise — better to reject than guess)."""
    schema = TABLE_SCHEMAS.get(target_table)
    if schema is None:
        return [f"no CSV schema defined for target_table '{target_table}'. "
                f"Supported: {list(TABLE_SCHEMAS)}"]

    errors = []
    header_set = set(headers)
    missing = [c for c in schema["required"] if c not in header_set]
    if missing:
        errors.append(f"missing required columns: {missing}")

    known = set(schema["required"]) | set(schema["optional"])
    unknown = [h for h in headers if h not in known]
    if unknown:
        errors.append(f"unrecognized columns (typo, or need adding to the schema): {unknown}")

    return errors
