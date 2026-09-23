"""
SurrealDB client for the Django platform — same HTTP /sql approach as the existing
vitasale_intelligence/db.py (no SurrealDB SDK; the REST endpoint is simpler and more
predictable across versions than v3.0.5's Python client compatibility, per that file's own
note). Config comes from Django settings.SURREALDB, not a standalone config.yaml, since
Django now owns configuration for the whole platform.

This is the ONLY thing in the platform that should ever construct raw SurrealQL — everything
else goes through apps/datastore/repositories/, per architecture doc §2.
"""
import base64
import functools

import requests
from django.conf import settings


class SurrealDB:
    def __init__(self):
        cfg = settings.SURREALDB
        self.endpoint = cfg["ENDPOINT"].rstrip("/")
        self.namespace = cfg["NAMESPACE"]
        self.database = cfg["DATABASE"]
        auth = f"{cfg['USERNAME']}:{cfg['PASSWORD']}".encode()
        self._headers = {
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "surreal-ns": self.namespace,
            "surreal-db": self.database,
            "Authorization": "Basic " + base64.b64encode(auth).decode(),
        }

    def query(self, sql: str) -> list[dict]:
        """Run one or more ;-separated SurrealQL statements. Returns the list of
        per-statement result envelopes, in order."""
        resp = requests.post(f"{self.endpoint}/sql", data=sql.encode("utf-8"),
                              headers=self._headers, timeout=120)
        resp.raise_for_status()
        results = resp.json()
        for r in results:
            if r.get("status") != "OK":
                raise RuntimeError(f"SurrealDB query failed: {r}")
        return results

    def select(self, sql: str) -> list[dict]:
        """Convenience: run a single SELECT-shaped statement, return its result rows.

        ⚠️ Do not add ORDER BY expecting completeness without testing it first — confirmed
        2026-08-26 that ORDER BY on at least one table silently truncated results (90 of 281
        rows, no error). See PHASE1_DATA_AND_LOGIC_REFERENCE.md item 9. Sort in Python."""
        results = self.query(sql)
        return results[0]["result"] if results else []

    def health(self) -> bool:
        resp = requests.get(f"{self.endpoint}/health", timeout=10)
        return resp.status_code == 200


@functools.lru_cache(maxsize=1)
def get_client() -> SurrealDB:
    """Process-local singleton — avoids re-reading settings / re-building auth headers on
    every repository call. Safe to share: the client is stateless beyond its own config."""
    return SurrealDB()
