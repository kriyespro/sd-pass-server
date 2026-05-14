from django.contrib import admin

from .models import ProjectRoute


@admin.register(ProjectRoute)
class ProjectRouteAdmin(admin.ModelAdmin):
    list_display = ('fqdn', 'project', 'status', 'updated_at')
    list_filter = ('status',)
    search_fields = ('fqdn', 'project__slug')
