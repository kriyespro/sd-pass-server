from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'owner',
        'project_type',
        'status',
        'subdomain',
        'custom_hostname',
        'custom_hostname_verified',
        'is_deleted',
        'created_at',
    )
    list_filter = ('project_type', 'status', 'is_deleted')
    search_fields = ('name', 'slug', 'subdomain', 'owner__email')
    readonly_fields = ('created_at',)
