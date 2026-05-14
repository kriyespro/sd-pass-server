from django.contrib import admin

from .models import ProjectUpload


@admin.register(ProjectUpload)
class ProjectUploadAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'project', 'owner', 'status', 'size_bytes', 'created_at')
    list_filter = ('status',)
    search_fields = ('original_name', 'project__slug', 'owner__email')
    readonly_fields = ('created_at', 'size_bytes', 'original_name')
