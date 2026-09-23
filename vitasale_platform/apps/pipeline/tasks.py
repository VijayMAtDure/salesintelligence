import logging

from celery import shared_task
from django.utils import timezone

from apps.pipeline.models import PipelineRun
from apps.pipeline.services.pipeline_runner import run_pipeline

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_pipeline_task(self, run_id: int):
    PipelineRun.objects.filter(pk=run_id).update(celery_task_id=self.request.id)
    try:
        run_pipeline(run_id)
    except Exception as exc:
        logger.exception("Unhandled error running pipeline run %s", run_id)
        # Don't clobber a CANCELLED status the cancel action already wrote — see
        # pipeline_runner.run_pipeline's cancellation-guard comments for the full mechanism.
        PipelineRun.objects.filter(pk=run_id).exclude(status="CANCELLED").update(
            status="FAILED", error_message=f"unhandled: {exc}", finished_at=timezone.now(),
        )
        raise
