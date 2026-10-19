"""
URL configuration — API-first per architecture doc §1 point 2. Everything user-facing lives
under /api/v1/, versioned from day one (§8's flagged gap) so a later breaking change doesn't
force every existing client to move in lockstep.
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.health_views import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),

    # Kubernetes liveness/readiness probes - see apps/core/health_views.py.
    path("health/live", live),
    path("health/ready", ready),

    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path("api/v1/training/", include("apps.training.urls")),
    path("api/v1/pipeline/", include("apps.pipeline.urls")),
    path("api/v1/ingestion/", include("apps.ingestion.urls")),
    path("api/v1/inference/", include("apps.inference.urls")),
    path("api/v1/analytics/", include("apps.analytics.urls")),
    path("api/v1/assistant/", include("apps.assistant.urls")),

    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
