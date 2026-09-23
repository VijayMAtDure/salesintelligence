"""
Python -> SurrealQL literal serialization and bulk-write helpers. Ported unchanged from
vitasale_intelligence/load.py — no SurrealDB SDK is used (see surreal_client.py's rationale),
so this module owns the Python -> SurrealQL literal mapping explicitly, keyed off the exact
DDL types of each target table.
"""
from apps.datastore.surreal_client import SurrealDB


def to_surql(value, kind: str = "auto") -> str:
    if value is None:
        return "NONE"
    if kind == "record":
        return str(value)  # unquoted table:id reference, e.g. organisation:4
    if kind == "datetime":
        return f"d'{value}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(to_surql(v) for v in value) + "]"
    if isinstance(value, dict):
        parts = [f"{k}: {to_surql(v)}" for k, v in value.items()]
        return "{" + ", ".join(parts) + "}"
    raise TypeError(f"cannot serialize {type(value)} for value {value!r}")


def row_to_surql_object(row: dict, field_kinds: dict) -> str:
    parts = [f"{k}: {to_surql(v, field_kinds.get(k, 'auto'))}" for k, v in row.items()]
    return "{" + ", ".join(parts) + "}"


def bulk_insert(db: SurrealDB, table: str, rows: list[dict], field_kinds: dict,
                 batch_size: int = 300) -> int:
    """batch_size default is 300; tables with large per-row payloads (e.g. anything carrying
    a full JSON blob) may need a smaller batch — confirmed 2026-08 that call_event needed 50,
    not 300, to avoid an HTTP 413. Pass batch_size explicitly for such tables."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        objs = ", ".join(row_to_surql_object(r, field_kinds) for r in batch)
        db.query(f"INSERT INTO {table} [{objs}];")
        total += len(batch)
    return total


def upsert_by_key(db: SurrealDB, table: str, rows: list[dict], key_fields: list[str],
                   field_kinds: dict) -> int:
    """One UPSERT per row, matched on key_fields — safe to rerun (creates if the key doesn't
    exist, updates in place if it does). Needed anywhere a job might re-touch rows that
    already exist from a prior run (incremental re-processing), where a plain INSERT would
    hit a unique-index violation."""
    total = 0
    for row in rows:
        set_parts = [f"{k} = {to_surql(v, field_kinds.get(k, 'auto'))}" for k, v in row.items()]
        where_parts = []
        for k in key_fields:
            v = row[k]
            kind = field_kinds.get(k, "auto")
            where_parts.append(f"{k} = {to_surql(v, kind) if v is not None else 'NONE'}")
        set_clause = ", ".join(set_parts)
        where_clause = " AND ".join(where_parts)
        db.query(f"UPSERT {table} SET {set_clause} WHERE {where_clause};")
        total += 1
    return total
