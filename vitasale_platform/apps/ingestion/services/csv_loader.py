"""
CSV upload -> validated -> merged directly into the real source table (call_decision is
SCHEMALESS in SurrealDB — it's the client's own raw table, not one of our DEFINE'd ones — so
a validated CSV row can be inserted as a new call_decision record with no DDL mismatch risk).

Runs inside the Celery worker on the "pipeline" queue (same as pipeline transforms — CSV
loading is lightweight I/O, doesn't need its own dedicated queue).

Re-upload safety (2026-09-18): a "full export" re-upload can legitimately overlap with rows
already in call_decision (same calls, re-exported alongside genuinely new ones). There's no
natural unique key on this schemaless table to upsert against, so instead this filters
incoming rows by processed_at against the max processed_at already present — same date-cutoff
idea run_features.py's incremental mode already relies on, and for the same underlying reason:
call_decision.processed_at is confirmed messy in production (NONE, the literal string
'not_mentioned', and naive-IST strings all appear alongside proper UTC ISO strings — see
apps.datastore.timeutil's parse_flexible docstring and run_features.py's own comment on this
exact field). Unparseable existing values are skipped when computing the cutoff rather than
raising, so one bad historical row can't block every future upload.

Known, accepted limitation: this assumes the export only APPENDS new rows past that cutoff —
a corrected/updated value for a call we already have (e.g. a disposition_tag fixed after the
fact) will be silently skipped, not re-ingested. If that ever needs to change, this needs a
real per-row key instead of a date cutoff.
"""
import csv
import hashlib
import io

from django.utils import timezone

from apps.datastore.surql_writer import bulk_insert
from apps.datastore.surreal_client import get_client
from apps.datastore.timeutil import parse_flexible
from apps.ingestion.models import IngestionEvent, IngestionJob
from apps.ingestion.services.csv_schemas import validate_headers

DATETIME_COLUMNS = {"processed_at"}


def _safe_parse(value):
    """None on anything unparseable (missing, blank, or garbage like the literal string
    'not_mentioned' — confirmed present in real call_decision.processed_at data) rather than
    raising, so one bad row never blocks computing a cutoff from the rest."""
    if not value:
        return None
    try:
        return parse_flexible(value)
    except (ValueError, OverflowError):
        return None


def _latest_existing_processed_at(db, target_table: str):
    """Max processed_at already in target_table, or None if the table is empty/has no
    parseable dates yet (first upload — nothing to filter against)."""
    rows = db.select(f"SELECT processed_at FROM {target_table};")
    parsed = [_safe_parse(r.get("processed_at")) for r in rows]
    parsed = [p for p in parsed if p is not None]
    return max(parsed) if parsed else None


def compute_checksum(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _log(job: IngestionJob, event_type: str, detail: dict | None = None):
    IngestionEvent.objects.create(job=job, event_type=event_type, detail=detail or {})


def run_csv_ingestion(job_id: int) -> None:
    job = IngestionJob.objects.select_related("uploaded_file").get(pk=job_id)
    uf = job.uploaded_file
    job.status = "RUNNING"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    _log(job, "STARTED", {"target_table": uf.target_table, "file": uf.original_filename})

    with uf.file.open("rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")  # -sig strips a BOM if Excel added one
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []

    errors = validate_headers(uf.target_table, headers)
    if errors:
        uf.validation_errors = errors
        uf.save(update_fields=["validation_errors"])
        job.status = "FAILED"
        job.error_message = "; ".join(errors)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        _log(job, "FAILED", {"reason": "DATA_VALIDATION_FAILED", "errors": errors})
        return

    rows = list(reader)
    for r in rows:
        r["_csv_upload_id"] = str(uf.id)  # provenance: which upload this row came from

    field_kinds = {c: "datetime" for c in DATETIME_COLUMNS}
    db = get_client()

    cutoff = _latest_existing_processed_at(db, uf.target_table)
    if cutoff is None:
        new_rows, skipped_overlap, unparseable = rows, 0, 0
    else:
        new_rows, skipped_overlap, unparseable = [], 0, 0
        for r in rows:
            parsed = _safe_parse(r.get("processed_at"))
            if parsed is None:
                unparseable += 1  # can't place it relative to the cutoff — insert rather
                new_rows.append(r)  # than silently drop a row that might genuinely be new
            elif parsed > cutoff:
                new_rows.append(r)
            else:
                skipped_overlap += 1
        _log(job, "FILTERED", {
            "cutoff": cutoff.isoformat(), "total_rows": len(rows),
            "new_rows": len(new_rows), "skipped_as_already_present": skipped_overlap,
            "unparseable_processed_at_inserted_anyway": unparseable,
        })

    n = bulk_insert(db, uf.target_table, new_rows, field_kinds, batch_size=200) if new_rows else 0

    uf.row_count = n
    uf.save(update_fields=["row_count"])
    job.status = "SUCCEEDED"
    job.rows_ingested = n
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "rows_ingested", "finished_at"])
    _log(job, "SUCCEEDED", {
        "rows_ingested": n, "rows_in_file": len(rows),
        "skipped_as_already_present": len(rows) - n,
    })
