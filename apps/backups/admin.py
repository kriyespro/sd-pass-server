from django.contrib import admin

from .models import BackupJob


@admin.register(BackupJob)
class BackupJobAdmin(admin.ModelAdmin):
    list_display = ('project', 'status', 'created_at', 'finished_at')
    list_filter = ('status',)
