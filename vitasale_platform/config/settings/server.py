"""
Server settings — for running on the GPU box (204.12.205.2) itself, co-located with
Postgres/Redis/the GPU worker. Not the same as prod.py: this box is internal, not yet
internet-exposed with a real domain/TLS, so the strict HTTPS-only settings in prod.py would
just break local testing on the box for no benefit right now. Promote to prod.py's settings
once this is actually deployed behind a real domain.
"""
from datetime import timedelta

from .base import *  # noqa: F401,F403

DEBUG = env.bool("DJANGO_DEBUG", default=True)
# llm.imonitorplus.com added when this service was put behind the shared nginx host (same
# box, reverse-proxied under /vitasale-intelligence/ alongside the vitasale/vitalaillm
# services) — nginx forwards the original Host header, so Django's own ALLOWED_HOSTS check
# sees the domain, not the bare IP, and rejects it (400 DisallowedHost) without this.
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["204.12.205.2", "localhost", "127.0.0.1", "llm.imonitorplus.com"],
)

# Effectively non-expiring on THIS box only (internal pilot/testing, not internet-exposed), per
# explicit request: a single token should work indefinitely for scripting/curl, not just for a
# few days. SimpleJWT always stamps an `exp` claim (no real "no expiry" flag), so "never" here
# means "100 years" in practice, not literally unbounded. Scoped to server.py specifically, not
# base.py, so prod.py stays on the short-lived secure default when this platform actually goes
# in front of a real client. A token that never expires has no automatic cutoff if it leaks —
# treat any token minted under this setting as a long-lived credential, not a throwaway one.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=365 * 100),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=365 * 100),
}

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[
    "http://localhost:5173", "http://127.0.0.1:5173",
    # Frontend build served on this box (2026-09-18) at :5173, reached by IP -- cross-port from
    # the API's own :9018/llm.imonitorplus.com origin, so needs its own explicit CORS entry.
    "http://204.12.205.2:5173",
])
CORS_ALLOW_CREDENTIALS = True
