"""
Assistant -- conversational memory for the sales intelligence chat agent (see
SALES_INTELLIGENCE_AGENT_PLAN.md). ConversationMessage stores the full OpenAI message shape
(role/content/tool_calls/tool_call_id) so a session's history can be replayed verbatim on the
next turn -- this is the memory that would otherwise need Flowise to provide.
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ConversationSession(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assistant_sessions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ConversationSession#{self.pk} ({self.user})"


class ConversationMessage(models.Model):
    ROLE_CHOICES = [("user", "User"), ("assistant", "Assistant"), ("tool", "Tool")]

    session = models.ForeignKey(ConversationSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)
    # Raw OpenAI tool_calls array, present only on assistant messages that invoked a tool.
    tool_calls = models.JSONField(default=list, blank=True)
    # Present only on "tool" role messages -- links the result back to the call that made it.
    tool_call_id = models.CharField(max_length=100, blank=True)
    tool_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.session_id}:{self.role}@{self.created_at}"
