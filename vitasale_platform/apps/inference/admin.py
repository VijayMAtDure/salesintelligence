from django.contrib import admin

from .models import InferenceJob


@admin.register(InferenceJob)
class InferenceJobAdmin(admin.ModelAdmin):
    list_display = ("id", "track", "target", "model_version", "status", "triggered_by", "created_at")
    list_filter = ("track", "status")
