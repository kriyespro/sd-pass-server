from django.contrib import admin

from .models import WordPressInstance


@admin.register(WordPressInstance)
class WordPressInstanceAdmin(admin.ModelAdmin):
    list_display = ('project', 'wp_admin_user', 'wp_admin_email', 'created_at')
    search_fields = ('project__name', 'project__slug', 'wp_admin_email')
    readonly_fields = ('created_at', 'updated_at')
