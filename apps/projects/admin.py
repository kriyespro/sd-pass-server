from django.conf import settings
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .models import Project, ProjectSubfolder, WebsiteOverview


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


def _build_site_url(obj):
    scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'http')
    base = getattr(settings, 'STUDENT_APPS_BASE_DOMAIN', 'apps.localhost').strip('.')
    port = getattr(settings, 'STUDENT_SITE_HTTP_PORT', 0)
    port_seg = f':{port}' if port else ''
    subfolder = (obj.site_subfolder or '').strip('/')
    path = f'/{subfolder}/' if subfolder else '/'
    return f'{scheme}://{obj.subdomain}.{base}{port_seg}{path}'


@admin.register(WebsiteOverview)
class WebsiteOverviewAdmin(admin.ModelAdmin):
    list_display = (
        'project_link',
        'owner',
        'subdomain_link',
        'custom_domain_link',
        'subfolder_display',
        'status',
        'is_deleted',
        'delete_action',
    )
    list_filter = ('project_type', 'status', 'is_deleted')
    search_fields = ('name', 'subdomain', 'owner__email', 'custom_hostname')
    actions = [_soft_delete, _restore, _purge_with_traefik]
    show_full_result_count = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Project', ordering='name')
    def project_link(self, obj):
        url = reverse('admin:projects_project_change', args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.name)

    @admin.display(description='Subdomain URL')
    def subdomain_link(self, obj):
        url = _build_site_url(obj)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}.{}</a>',
            url,
            obj.subdomain,
            getattr(settings, 'STUDENT_APPS_BASE_DOMAIN', '').strip('.'),
        )

    @admin.display(description='Custom Domain')
    def custom_domain_link(self, obj):
        host = (obj.custom_hostname or '').strip()
        if not host:
            return '—'
        scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', 'https')
        url = f'{scheme}://{host}/'
        verified = obj.custom_hostname_verified
        badge = '✅' if verified else '⏳'
        return format_html('<a href="{}" target="_blank" rel="noopener">{} {}</a>', url, badge, host)

    @admin.display(description='Subfolder')
    def subfolder_display(self, obj):
        sf = (obj.site_subfolder or '').strip('/')
        return sf or '/ (root)'

    @admin.display(description='Delete')
    def delete_action(self, obj):
        url = reverse('admin:projects_project_delete', args=[obj.pk])
        return format_html(
            '<a href="{}" style="color:#ba2121;font-weight:bold;">Delete</a>', url
        )
