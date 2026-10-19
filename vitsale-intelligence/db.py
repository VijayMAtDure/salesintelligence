"""
SurrealDB connection helper. Thin wrapper over the HTTP /sql endpoint —
same pattern already validated manually against this instance (see
PHASE1_DATA_AND_LOGIC_REFERENCE.md). No SurrealDB SDK dependency: v3.0.5's
Python client compatibility wasn't verified, and the REST endpoint is simple
enough that a raw requests wrapper is more predictable across versions.
"""
import base64
import requests
import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class SurrealDB:
    def __init__(self, config: dict | None = None):
        cfg = (config or load_config())["database"]
        self.endpoint = cfg["endpoint"].rstrip("/")
        self.namespace = cfg["namespace"]
        self.database = cfg["database"]
        auth = f"{cfg['username']}:{cfg['password']}".encode()
        self._headers = {
            "Content-Type": "text/plain",
            "Accept": "application/json",
            "surreal-ns": self.namespace,
            "surreal-db": self.database,
            "Authorization": "Basic " + base64.b64encode(auth).decode(),
        }

    def query(self, sql: str) -> list[dict]:
        """Run one or more ;-separated SurrealQL statements. Returns the list
        of per-statement result envelopes ({"status", "result", ...}), in order."""
        resp = requests.post(f"{self.endpoint}/sql", data=sql.encode("utf-8"),
                              headers=self._headers, timeout=120)
        resp.raise_for_status()
        results = resp.json()
        for r in results:
            if r.get("status") != "OK":
                raise RuntimeError(f"SurrealDB query failed: {r}")
        return results

    def select(self, sql: str) -> list[dict]:
        """Convenience: run a single SELECT-shaped statement, return its result rows."""
        results = self.query(sql)
        return results[0]["result"] if results else []

    def health(self) -> bool:
        resp = requests.get(f"{self.endpoint}/health", timeout=10)
        return resp.status_code == 200


if __name__ == "__main__":
    db = SurrealDB()
    print("health:", db.health())
    print(db.select("SELECT count() FROM call_decision GROUP ALL;"))
