"""
Production settings. Postgres via DATABASE_URL env var — see DJANGO_PLATFORM_ARCHITECTURE.md
§2 for why Postgres (not SurrealDB) is the control-plane store. Nothing here has been
deployed/exercised yet; fill in ALLOWED_HOSTS / CORS_ALLOWED_ORIGINS for the real domain
before first deploy.
"""
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DATABASES = {
    "default": env.db("DATABASE_URL"),  # e.g. postgres://user:pass@host:5432/vitasale_platform
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
