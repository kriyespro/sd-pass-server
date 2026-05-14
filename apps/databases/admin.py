from django.contrib import admin

from .models import DatabaseInstance


@admin.register(DatabaseInstance)
class DatabaseInstanceAdmin(admin.ModelAdmin):
    list_display = ('project', 'name', 'engine', 'host', 'port', 'created_at')
    search_fields = ('project__slug', 'name')
