from rest_framework import mixins, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ConversationMessage, ConversationSession
from .serializers import (
    ChatRequestSerializer, ConversationMessageSerializer, ConversationSessionSerializer,
)
from .services.agent import run_turn


class ConversationSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                                  viewsets.GenericViewSet):
    """Read-only -- sessions are created implicitly by ChatView's first message, not via a
    direct POST here."""
    serializer_class = ConversationSessionSerializer

    def get_queryset(self):
        return ConversationSession.objects.filter(user=self.request.user)


class ChatView(APIView):
    """POST {session_id?, message} -> {session_id, reply, messages}. session_id omitted or
    null starts a new session. Conversation memory lives entirely in ConversationMessage rows
    -- the full history is replayed to OpenAI on every turn (the plan doc's decision to keep
    memory simple rather than reach for Flowise for it)."""

    def post(self, request):
        req = ChatRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        session_id = req.validated_data.get("session_id")
        if session_id:
            session = ConversationSession.objects.filter(pk=session_id, user=request.user).first()
            if session is None:
                return Response({"detail": "session not found"}, status=404)
        else:
            session = ConversationSession.objects.create(user=request.user)

        history = [
            {
                "role": m.role, "content": m.content,
                **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
            }
            for m in session.messages.all()
        ]
        user_message = req.validated_data["message"]
        history.append({"role": "user", "content": user_message})
        ConversationMessage.objects.create(session=session, role="user", content=user_message)

        reply, new_messages = run_turn(history, request.user)

        for nm in new_messages:
            ConversationMessage.objects.create(
                session=session, role=nm["role"], content=nm.get("content") or "",
                tool_calls=nm.get("tool_calls") or [], tool_call_id=nm.get("tool_call_id", ""),
                tool_name=nm.get("tool_name", ""),
            )

        return Response({
            "session_id": session.id,
            "reply": reply,
            "messages": ConversationMessageSerializer(session.messages.all(), many=True).data,
        })
