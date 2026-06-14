from django.contrib import admin

from .models import EmailTemplate, SMTPConfig


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['template_type', 'subject', 'is_active', 'updated_at']
    list_filter = ['is_active', 'template_type']


@admin.register(SMTPConfig)
class SMTPConfigAdmin(admin.ModelAdmin):
    list_display = ['from_name', 'from_email', 'host', 'port', 'use_tls', 'is_active']
