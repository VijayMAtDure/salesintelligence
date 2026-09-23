from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import InferenceJobViewSet, NarrativeSandboxView

router = DefaultRouter()
router.register("jobs", InferenceJobViewSet, basename="inference-job")

urlpatterns = router.urls + [
    path("narrative-sandbox/", NarrativeSandboxView.as_view(), name="narrative-sandbox"),
]
