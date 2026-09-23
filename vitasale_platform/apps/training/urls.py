from rest_framework.routers import DefaultRouter

from .views import ModelVersionViewSet, TrainingJobViewSet

router = DefaultRouter()
router.register("jobs", TrainingJobViewSet, basename="training-job")
router.register("models", ModelVersionViewSet, basename="model-version")

urlpatterns = router.urls
