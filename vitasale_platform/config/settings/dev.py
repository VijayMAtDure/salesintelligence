"""
Local development settings. SQLite — zero setup, no Postgres/Docker required (neither was
available in the dev environment when this was scaffolded; see DJANGO_PLATFORM_ARCHITECTURE.md
§2 for why Postgres is still the right call for prod — this is a dev-only substitute, not a
design change). Swapping to Postgres later is a DATABASES change here, nothing else, as long
as model fields stay portable (no Postgres-only field types).
"""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# React dev server (Vite default port) — explicit allow-list, never "*" (architecture doc §5.4)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True
