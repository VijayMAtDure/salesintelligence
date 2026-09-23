import logging

from celery import shared_task
from django.utils import timezone

from apps.ingestion.models import IngestionJob
from apps.ingestion.services.csv_loader import run_csv_ingestion

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_csv_ingestion_task(self, job_id: int):
    IngestionJob.objects.filter(pk=job_id).update(celery_task_id=self.request.id)
    try:
        run_csv_ingestion(job_id)
    except Exception as exc:
        logger.exception("Unhandled error running CSV ingestion job %s", job_id)
        IngestionJob.objects.filter(pk=job_id).update(
            status="FAILED", error_message=f"unhandled: {exc}", finished_at=timezone.now(),
        )
        raise
