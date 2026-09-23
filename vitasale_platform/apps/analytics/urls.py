from django.urls import path

from .views import NbaEffectivenessView, ResponseWindowSimView, ResponseWindowView, SystemMapView

urlpatterns = [
    path("nba-effectiveness/", NbaEffectivenessView.as_view(), name="nba-effectiveness"),
    path("response-window/", ResponseWindowView.as_view(), name="response-window"),
    path("response-window-sim/", ResponseWindowSimView.as_view(), name="response-window-sim"),
    path("system-map/", SystemMapView.as_view(), name="system-map"),
]
