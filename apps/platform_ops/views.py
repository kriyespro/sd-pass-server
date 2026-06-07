from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View

from apps.platform_ops.models import AssetOptimizationRun, PlatformBackup
from apps.platform_ops.services.asset_runner import optimization_interval
from apps.platform_ops.tasks import create_platform_backup_task, run_asset_optimization_task


class StaffOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('accounts:login')
    raise_exception = False

    def test_func(self) -> bool:
        u = self.request.user
        return u.is_authenticated and u.is_staff

    def handle_no_permission(self):
        return HttpResponseRedirect(reverse('home'))


class RunAssetOptimizationView(StaffOnlyMixin, View):
    def post(self, request):
        if AssetOptimizationRun.objects.filter(
            status__in=(
                AssetOptimizationRun.Status.PENDING,
                AssetOptimizationRun.Status.RUNNING,
            )
        ).exists():
            messages.warning(request, 'Asset optimization is already running.')
            return HttpResponseRedirect(reverse('admin_monitor:dashboard'))

        from django.utils import timezone

        run = AssetOptimizationRun.objects.create(
            status=AssetOptimizationRun.Status.PENDING,
            triggered_by=request.user,
            next_run_at=timezone.now() + optimization_interval(),
        )
        run_asset_optimization_task.delay(run.pk)
        messages.success(request, 'Asset optimization started (CSS, JS, and images).')
        return HttpResponseRedirect(reverse('admin_monitor:dashboard'))


class CreatePlatformBackupView(StaffOnlyMixin, View):
    def post(self, request):
        backup_type = request.POST.get('backup_type', PlatformBackup.BackupType.FULL)
        valid = {c[0] for c in PlatformBackup.BackupType.choices}
        if backup_type not in valid:
            backup_type = PlatformBackup.BackupType.FULL

        if PlatformBackup.objects.filter(
            status__in=(PlatformBackup.Status.PENDING, PlatformBackup.Status.RUNNING)
        ).exists():
            messages.warning(request, 'A backup is already in progress.')
            return HttpResponseRedirect(reverse('admin_monitor:dashboard'))

        backup = PlatformBackup.objects.create(
            status=PlatformBackup.Status.PENDING,
            backup_type=backup_type,
            created_by=request.user,
        )
        try:
            create_platform_backup_task.delay(backup.pk)
            messages.success(
                request,
                f'Backup queued ({backup.get_backup_type_display()}). '
                'Refresh in 1–2 min — ensure Celery worker is running.',
            )
        except Exception as exc:
            backup.status = PlatformBackup.Status.FAILED
            backup.error_message = f'Could not queue worker: {exc}'[:2000]
            backup.save(update_fields=['status', 'error_message'])
            messages.error(
                request,
                'Backup could not start — run: docker compose up -d worker',
            )
        return HttpResponseRedirect(reverse('admin_monitor:dashboard'))


class DownloadPlatformBackupView(StaffOnlyMixin, View):
    def get(self, request, backup_id: int):
        backup = get_object_or_404(
            PlatformBackup,
            pk=backup_id,
            status=PlatformBackup.Status.DONE,
        )
        from apps.platform_ops.services.backup import iter_backup_file, resolve_backup_path

        try:
            path = resolve_backup_path(backup)
        except (ValueError, FileNotFoundError):
            messages.error(
                request,
                f'Backup #{backup_id} ZIP missing on this server. '
                'Rebuild web+worker and check platform_backups volume.',
            )
            return HttpResponseRedirect(reverse('admin_monitor:dashboard'))

        response = StreamingHttpResponse(
            iter_backup_file(path),
            content_type='application/zip',
        )
        response['Content-Disposition'] = f'attachment; filename="{path.name}"'
        response['Content-Length'] = path.stat().st_size
        return response


class DeletePlatformBackupView(StaffOnlyMixin, View):
    def post(self, request, backup_id: int):
        backup = get_object_or_404(PlatformBackup, pk=backup_id)
        if backup.status in (
            PlatformBackup.Status.PENDING,
            PlatformBackup.Status.RUNNING,
        ):
            messages.warning(request, 'Cannot delete a backup that is still running.')
            return HttpResponseRedirect(reverse('admin_monitor:dashboard'))

        try:
            from apps.platform_ops.services.backup import delete_platform_backup

            delete_platform_backup(backup_id=backup.pk)
            messages.success(request, f'Backup #{backup_id} deleted.')
        except Exception as exc:
            messages.error(request, f'Could not delete backup: {exc}')
        return HttpResponseRedirect(reverse('admin_monitor:dashboard'))
