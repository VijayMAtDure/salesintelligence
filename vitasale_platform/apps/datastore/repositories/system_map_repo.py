"""
Generic table-count helper for the System Map page (apps.analytics.services.system_map) —
the one place this page needs raw counts across many tables that otherwise have no dedicated
repository. Kept here rather than one-off repo files per table, since this endpoint's only
actual query need is "how many rows does table X have right now."
"""
from apps.datastore.surreal_client import get_client


def count_table(table: str) -> int:
    db = get_client()
    rows = db.select(f"SELECT count() FROM {table} GROUP ALL;")
    return rows[0]["count"] if rows else 0
