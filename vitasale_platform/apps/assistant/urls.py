from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChatView, ConversationSessionViewSet

router = DefaultRouter()
router.register("sessions", ConversationSessionViewSet, basename="assistant-session")

urlpatterns = router.urls + [
    path("chat/", ChatView.as_view(), name="assistant-chat"),
]
