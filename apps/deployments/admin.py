from django.contrib import admin

from .models import Deployment


@admin.register(Deployment)
class DeploymentAdmin(admin.ModelAdmin):
    list_display = ('project', 'upload', 'status', 'created_at')
    list_filter = ('status',)
