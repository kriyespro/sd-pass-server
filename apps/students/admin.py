from django.contrib import admin

from .models import Batch, QuotaConfig, StudentProfile


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'trainer', 'requires_approval', 'created_at')
    filter_horizontal = ('students',)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'trainer', 'mobile')
    search_fields = ('user__email', 'mobile')


@admin.register(QuotaConfig)
class QuotaConfigAdmin(admin.ModelAdmin):
    list_display = ('user', 'ram_mb', 'cpu_cores', 'disk_gb', 'max_projects_display')
    search_fields = ('user__email',)

    @admin.display(description='Max projects')
    def max_projects_display(self, obj):
        if obj.max_projects is None:
            return '— (billing plan)'
        return obj.max_projects
