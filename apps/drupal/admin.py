from django.contrib import admin

from .models import DrupalInstance


@admin.register(DrupalInstance)
class DrupalInstanceAdmin(admin.ModelAdmin):
    list_display = ('project', 'admin_user', 'admin_email', 'site_name', 'created_at')
    search_fields = ('project__name', 'project__slug', 'admin_email', 'site_name')
    readonly_fields = ('created_at', 'updated_at')
