"""
Celery tasks for the training app. Routed to the gpu_training queue (config/settings/base.py
CELERY_TASK_ROUTES) — a worker started with --concurrency=1 bound to that queue is the ENTIRE
mechanism that makes "click Train again while one is running" safe: every click enqueues a
task here, Celery/Redis hold the queue, only one task executes at a time.
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.training.models import TrainingJob
from apps.training.services.job_runner import run_training_job

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_training_job_task(self, job_id: int):
    TrainingJob.objects.filter(pk=job_id).update(celery_task_id=self.request.id)
    try:
        run_training_job(job_id)
    except Exception as exc:
        # belt-and-suspenders: job_runner.run_training_job already handles its own known
        # failure modes (GPU unavailable, timeout, script error) and marks the job FAILED
        # with a specific reason. This catches anything unexpected so a bug in the runner
        # itself doesn't leave a job stuck RUNNING forever.
        logger.exception("Unhandled error running training job %s", job_id)
        TrainingJob.objects.filter(pk=job_id).update(
            status="FAILED", failure_reason="WORKER_ERROR",
            error_message=f"unhandled: {exc}", finished_at=timezone.now(),
        )
        raise
