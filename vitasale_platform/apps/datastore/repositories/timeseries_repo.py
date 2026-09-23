"""
Read access to sales_intelligence_timeseries — the forecasting track's training input
(hourly org/showroom/product buckets, doc §7 grain).
"""
from apps.datastore.surreal_client import get_client
from apps.datastore.timeutil import parse_iso


def count() -> int:
    db = get_client()
    rows = db.select("SELECT count() FROM sales_intelligence_timeseries GROUP ALL;")
    return rows[0]["count"] if rows else 0


def sample(limit: int = 20) -> list[dict]:
    db = get_client()
    return db.select(f"SELECT * FROM sales_intelligence_timeseries LIMIT {int(limit)};")


def all_sorted() -> list[dict]:
    """⚠️ Deliberately NOT `SELECT * ... ORDER BY bucket_start` — that silently truncated
    results on this exact table (see surreal_client.py's warning, and
    PHASE1_DATA_AND_LOGIC_REFERENCE.md item 9). Fetch unordered, sort in Python."""
    db = get_client()
    rows = db.select("SELECT * FROM sales_intelligence_timeseries;")
    rows.sort(key=lambda r: (r["item_id"], parse_iso(r["bucket_start"])))
    return rows


def for_item(item_id: str) -> list[dict]:
    """One series (one organisation/showroom/product combination), sorted."""
    rows = all_sorted()
    return [r for r in rows if r["item_id"] == item_id]
