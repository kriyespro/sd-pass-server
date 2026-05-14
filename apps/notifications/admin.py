from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'level', 'read_at', 'created_at')
    list_filter = ('level', 'read_at')
    search_fields = ('title', 'body', 'user__email')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
