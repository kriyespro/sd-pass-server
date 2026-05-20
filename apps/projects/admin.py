from django.contrib import admin, messages

from .models import Project, ProjectSubfolder


class ProjectSubfolderInline(admin.TabularInline):
    model = ProjectSubfolder
    extra = 0
    readonly_fields = ('path', 'updated_at')
    can_delete = True
    verbose_name_plural = 'Deployed subfolders'


@admin.register(ProjectSubfolder)
class ProjectSubfolderAdmin(admin.ModelAdmin):
    list_display = ('project', 'path', 'updated_at')
    list_filter = ('project__project_type',)
    search_fields = ('project__name', 'project__subdomain', 'path')
    readonly_fields = ('updated_at',)
    autocomplete_fields = ('project',)


def _soft_delete(modeladmin, request, queryset):
    updated = queryset.filter(is_deleted=False).update(is_deleted=True)
    messages.success(request, f'{updated} project(s) marked as deleted.')


_soft_delete.short_description = 'Soft-delete selected projects'


def _restore(modeladmin, request, queryset):
    updated = queryset.filter(is_deleted=True).update(is_deleted=False)
    messages.success(request, f'{updated} project(s) restored.')


_restore.short_description = 'Restore selected projects'


def _purge_with_traefik(modeladmin, request, queryset):
    from apps.domains.services import remove_project_router_file
    count = 0
    for project in queryset:
        try:
            remove_project_router_file(project)
        except Exception:
            pass
        project.delete()
        count += 1
    messages.success(request, f'{count} project(s) permanently deleted (Traefik config removed).')


_purge_with_traefik.short_description = 'Permanently delete + remove Traefik config'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'owner',
        'project_type',
        'status',
        'subdomain',
        'site_subfolder',
        'subfolder_count',
        'custom_hostname',
        'custom_hostname_verified',
        'is_deleted',
        'created_at',
    )
    list_filter = ('project_type', 'status', 'is_deleted')
    search_fields = ('name', 'slug', 'subdomain', 'owner__email')
    readonly_fields = ('created_at',)
    inlines = [ProjectSubfolderInline]
    actions = [_soft_delete, _restore, _purge_with_traefik]

    @admin.display(description='Subfolders')
    def subfolder_count(self, obj):
        return obj.subfolders.count()
