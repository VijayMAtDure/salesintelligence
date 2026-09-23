from django.contrib import admin

from .models import IngestionEvent, IngestionJob, UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "target_table", "row_count", "uploaded_by", "created_at")
    list_filter = ("target_table",)


class IngestionEventInline(admin.TabularInline):
    model = IngestionEvent
    extra = 0
    readonly_fields = ("event_type", "timestamp", "detail")
    can_delete = False


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ("id", "job_type", "mode", "status", "rows_ingested", "triggered_by", "created_at")
    list_filter = ("job_type", "mode", "status")
    inlines = [IngestionEventInline]
