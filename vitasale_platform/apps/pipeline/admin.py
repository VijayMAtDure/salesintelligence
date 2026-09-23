from django.contrib import admin

from .models import PipelineEvent, PipelineRun


class PipelineEventInline(admin.TabularInline):
    model = PipelineEvent
    extra = 0
    readonly_fields = ("stage", "event_type", "timestamp", "detail")
    can_delete = False


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "feature_version", "status", "current_stage", "triggered_by", "created_at")
    list_filter = ("mode", "status", "feature_version")
    inlines = [PipelineEventInline]
