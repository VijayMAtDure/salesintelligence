from rest_framework.routers import DefaultRouter

from .views import IngestionJobViewSet

router = DefaultRouter()
router.register("jobs", IngestionJobViewSet, basename="ingestion-job")

urlpatterns = router.urls
