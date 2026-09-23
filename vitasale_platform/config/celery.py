"""
Celery app config. The entire "GPU mandatory + never reject a click" mechanism (architecture
doc §7) rests on ONE thing: the gpu_training queue is consumed by a worker started with
--concurrency=1. That single flag is what guarantees only one training job ever touches the
GPU at a time, while CELERY_TASK_ROUTES (config/settings/base.py) sends every training task
there regardless of how many get submitted — they queue in Redis, never in application code.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("vitasale_platform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
