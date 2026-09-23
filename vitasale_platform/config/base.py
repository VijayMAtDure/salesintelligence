"""
Shared settings — dev.py and prod.py both import from here and override only what differs.

Secrets (SECRET_KEY, DB credentials, SurrealDB creds, GPU worker auth token, OpenAI key) are
read from environment variables via django-environ, never hardcoded — see §8 of
DJANGO_PLATFORM_ARCHITECTURE.md ("secrets management" gap flagged there). A .env file is
read locally for dev convenience (git-ignored); prod reads real environment variables.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-key-set-a-real-one-in-.env")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    # local apps
    "apps.core",
    "apps.ingestion",
    "apps.pipeline",
    "apps.training",
    "apps.inference",
    "apps.analytics",
]
# apps.datastore is deliberately NOT in INSTALLED_APPS — it has no Django models of its own
# (see architecture doc §2: it's a service layer over SurrealDB, not an ORM-backed app).

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # must sit above CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # CSV uploads land here (apps.ingestion.UploadedFile)

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB — CSVs beyond this stream to disk

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF: token-based auth for the React SPA (architecture doc §5.4), not session/CSRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "VITASale Sales Intelligence Platform API",
    "DESCRIPTION": "Ingestion, pipeline, training, and inference — see DJANGO_PLATFORM_ARCHITECTURE.md",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Current feature schema version — mirrors vitasale_intelligence/config.yaml's
# feature_version. Kept in sync manually for now (both configs describe the same underlying
# pipeline); if these ever diverge silently that's a real bug, not a design choice.
FEATURE_VERSION = env("FEATURE_VERSION", default="1.2")

# --- business timezone (doc §20: preserve organisation business timezone for business-hour
# features; see PHASE1_DATA_AND_LOGIC_REFERENCE.md for why naive timestamps must be localized
# to this, never assumed UTC) ---
BUSINESS_TZ_NAME = env("BUSINESS_TZ", default="Asia/Kolkata")

# --- SurrealDB connection (the actual feature/prediction data store — architecture doc §2) ---
SURREALDB = {
    "ENDPOINT": env("SURREALDB_ENDPOINT", default="http://127.0.0.1:8000"),
    "NAMESPACE": env("SURREALDB_NAMESPACE", default="salesdb2"),
    "DATABASE": env("SURREALDB_DATABASE", default="salesdb2"),
    "USERNAME": env("SURREALDB_USERNAME", default="root"),
    "PASSWORD": env("SURREALDB_PASSWORD", default="root"),
}

# --- GPU worker (architecture doc §7.3) — internal callback auth token, not DB creds ---
GPU_WORKER_CALLBACK_TOKEN = env("GPU_WORKER_CALLBACK_TOKEN", default="dev-only-change-me")
GPU_WORKER_HOST = env("GPU_WORKER_HOST", default="204.12.205.2")

# --- optional LLM narrative (architecture doc §5.2 / §6) ---
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")

# --- Core pipeline scripts (existing, proven vitasale_intelligence/*.py) — extract/events/
# features/aggregates, invoked via backfill.py / run_features.py subprocess, same reuse
# pattern as GPU_TRAINING_* below. Separate directory from GPU_TRAINING_SCRIPTS_DIR
# (server_scripts/) since these don't need a GPU and shouldn't compete for it. ---
PIPELINE_SCRIPTS_DIR = env(
    "PIPELINE_SCRIPTS_DIR", default="/nvme0n1-disk/vitsale-intelligence")
PIPELINE_PYTHON = env(
    "PIPELINE_PYTHON", default="/nvme0n1-disk/vitsale-intelligence/venv/bin/python")

# --- GPU training scripts (existing, proven vitasale_intelligence/server_scripts/) ---
# The job runner subprocess-invokes these rather than reimplementing training logic —
# they're already validated across the whole forecasting accuracy-enhancement effort
# (PHASE1_PHASE2_EXECUTION_FLOW.md). GPU_TRAINING_PYTHON is the shared venv per the user's
# explicit instruction to reuse it rather than create a second one.
GPU_TRAINING_SCRIPTS_DIR = env(
    "GPU_TRAINING_SCRIPTS_DIR", default="/nvme0n1-disk/vitsale-intelligence/scripts")
GPU_TRAINING_OUTPUT_DIR = env(
    "GPU_TRAINING_OUTPUT_DIR", default="/nvme0n1-disk/vitsale-intelligence/output")
GPU_TRAINING_PYTHON = env(
    "GPU_TRAINING_PYTHON", default="/nvme0n1-disk/vitsale-intelligence/venv/bin/python")

# --- Celery (architecture doc §7) ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TASK_ROUTES = {
    "apps.training.tasks.run_training_job_task": {"queue": "gpu_training"},
    "apps.pipeline.tasks.run_pipeline_task": {"queue": "pipeline"},
    "apps.ingestion.tasks.run_csv_ingestion_task": {"queue": "pipeline"},
    "apps.inference.tasks.run_inference_task": {"queue": "pipeline"},
    "apps.inference.tasks.generate_narrative_task": {"queue": "pipeline"},
}
