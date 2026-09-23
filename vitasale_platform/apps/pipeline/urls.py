from rest_framework.routers import DefaultRouter

from .views import PipelineRunViewSet

router = DefaultRouter()
router.register("runs", PipelineRunViewSet, basename="pipeline-run")

urlpatterns = router.urls
