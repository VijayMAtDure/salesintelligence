"""
Settings for running as the "forecast" pod in the vitasale-k8s Helm chart.

Not the same as server.py: that module hardcodes the GPU box's own IP/hostname as
defaults because it is that one specific, known machine. This module takes nothing for
granted - every backing service (Postgres, Redis, SurrealDB) is reached through an
in-cluster Service DNS name injected by the chart as a plain env var, never a hardcoded
default, so the same image works in any namespace/release.

DATABASE_URL / CELERY_BROKER_URL / CELERY_RESULT_BACKEND are NOT built here - the chart
assembles them directly using Kubernetes' own $(VAR) env-var expansion (a password from a
Secret, substituted into another env var's value within the same container spec - see
charts/vitasale/templates/31-forecast.yaml), and base.py's env("DATABASE_URL")/
env("CELERY_BROKER_URL") already read whatever lands in those two names. Nothing to
override here for either.

GPU_TRAINING_* / PIPELINE_* point at the stub_scripts/ shipped in this image (see that
directory's README) rather than the real vitasale_intelligence scripts - those stay on
the GPU box and are out of scope for this pod. See job_runner.py's GPU_HEALTH_CHECK_MODE
for how the GPU-mandatory precondition is handled here without pretending a GPU exists.
"""
from pathlib import Path

from .base import *  # noqa: F401,F403

DEBUG = env.bool("DJANGO_DEBUG", default=False)
# Internal test/staging pod behind the chart's own ingress - "*" is acceptable here the
# same way it would not be in prod.py. Override with DJANGO_ALLOWED_HOSTS once this is
# reachable from anywhere less controlled than the cluster's internal ingress class.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# whitenoise, inserted right after SecurityMiddleware per its own docs - there is no nginx
# sidecar serving /static/ in this pod, so Django (via whitenoise) has to.
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405 - defined by the base.py import above
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
# ⚠️ Must keep "default" (media/FileField uploads - apps.ingestion.UploadedFile.file)
# alongside "staticfiles" here. Confirmed live: overriding STORAGES with only
# "staticfiles" silently drops Django's built-in "default" FileSystemStorage entry,
# and every FileField save then fails with InvalidStorageError - not caught by any
# test, only by actually uploading a file through the running pod.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- GPU_TRAINING_SCRIPTS_DIR now points at the REAL vitsale-intelligence/scripts/ baked
# into this image (predict.py is the genuine inference script, real trained models are
# baked in under /app/models) - see docker/forecast-api's build-and-push.sh changes. Real
# train_forecast.py/train_propensity.py were never handed over (training stays out of
# scope), so this directory has COPIES of the stub versions sitting alongside the real
# predict.py, purely so a Train click still exercises the real job lifecycle (locking,
# event trail, ModelVersion/is_latest) without pretending real GPU training happened -
# only *inference* against the real pre-trained artifacts is real here.
_real_scripts_dir = Path("/app/vitsale-intelligence/scripts")
_stub_scripts_dir = Path(__file__).resolve().parent.parent.parent / "stub_scripts"
_scripts_dir = _real_scripts_dir if _real_scripts_dir.exists() else _stub_scripts_dir
GPU_TRAINING_PYTHON = env("GPU_TRAINING_PYTHON", default="python3")
GPU_TRAINING_SCRIPTS_DIR = env("GPU_TRAINING_SCRIPTS_DIR", default=str(_scripts_dir))
GPU_TRAINING_OUTPUT_DIR = env("GPU_TRAINING_OUTPUT_DIR", default="/tmp/stub_output")
PIPELINE_PYTHON = env("PIPELINE_PYTHON", default="python3")
PIPELINE_SCRIPTS_DIR = env("PIPELINE_SCRIPTS_DIR", default=str(_stub_scripts_dir))

# See job_runner.py: "stub" skips the real torch.cuda subprocess check (there is no GPU on
# this box) and logs that it did so, rather than either lying about GPU availability or
# blocking every training job forever. Never set to "stub" outside this settings module.
GPU_HEALTH_CHECK_MODE = env("GPU_HEALTH_CHECK_MODE", default="stub")
