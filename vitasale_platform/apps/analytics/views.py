from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.services import nba_effectiveness, response_window, response_window_sim, system_map


class NbaEffectivenessView(APIView):
    """GET-only, computed live on each request -- the underlying tables (feature_snapshot,
    outcome_sim) are small (5,383 rows) and static at this pilot's current scale, so there's
    no caching/background-job complexity worth adding yet. Revisit if either table grows large
    enough to make the join slow, or once it's driven by a live-growing real outcome table."""

    def get(self, request):
        return Response(nba_effectiveness.compute())


class ResponseWindowView(APIView):
    """GET-only, computed live — same rationale as NbaEffectivenessView."""

    def get(self, request):
        return Response(response_window.compute())


class ResponseWindowSimView(APIView):
    """GET-only. Simulated-on-both-axes comparison — see response_window_sim.py's docstring."""

    def get(self, request):
        return Response(response_window_sim.compute())


class SystemMapView(APIView):
    """GET-only. The 'jungle map' page — see system_map.py's docstring."""

    def get(self, request):
        return Response(system_map.compute())
