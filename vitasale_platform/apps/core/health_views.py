"""Health endpoints for the forecast-api pod (see vitasale-k8s's
charts/vitasale/templates/31-forecast.yaml for the probes that call these).

/health/live  - the process is alive. Never touches Postgres/SurrealDB, so a slow
                dependency never gets the pod killed by the liveness probe.
/health/ready - Postgres AND SurrealDB both answer. Returns 503 until both hold, which is
                what keeps the Kubernetes Service from routing traffic to a pod that has
                not finished migrating or cannot reach its data stores yet.
"""
from __future__ import annotations

import requests
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def live(_request):
    return JsonResponse({"status": "alive"})


def ready(_request):
    checks: dict[str, str] = {}
    ok = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["postgres"] = "up"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"unreachable: {type(exc).__name__}"
        ok = False

    endpoint = settings.SURREALDB["ENDPOINT"]
    try:
        resp = requests.get(f"{endpoint}/health", timeout=3)
        checks["surrealdb"] = "up" if resp.ok else f"http {resp.status_code}"
        ok = ok and resp.ok
    except Exception as exc:  # noqa: BLE001
        checks["surrealdb"] = f"unreachable: {type(exc).__name__}"
        ok = False

    return JsonResponse(
        {"status": "ready" if ok else "not-ready", "checks": checks},
        status=200 if ok else 503,
    )
