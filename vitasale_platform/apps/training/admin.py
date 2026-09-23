from django.contrib import admin

from .models import ModelVersion, TrainingEvent, TrainingJob


class TrainingEventInline(admin.TabularInline):
    model = TrainingEvent
    extra = 0
    readonly_fields = ("event_type", "timestamp", "detail", "gpu_host")
    can_delete = False


@admin.register(TrainingJob)
class TrainingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "track", "target", "transform", "status", "queue_position",
        "gpu_host", "triggered_by", "queued_at",
    )
    list_filter = ("track", "status", "transform")
    inlines = [TrainingEventInline]


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "track", "target", "version_label", "model_name",
        "validation_metric", "validation_score", "is_latest", "provenance", "created_at",
    )
    list_filter = ("track", "is_latest", "provenance")
    list_editable = ()  # is_latest changes go through the promote/ endpoint, not raw admin edit
