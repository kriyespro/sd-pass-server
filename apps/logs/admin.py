from django.contrib import admin

from .models import LogEntry


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('project', 'kind', 'created_at', 'message_preview')
    list_filter = ('kind',)
    search_fields = ('message', 'project__slug')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    @admin.display(description='Message')
    def message_preview(self, obj):
        return (obj.message[:120] + '…') if len(obj.message) > 120 else obj.message
