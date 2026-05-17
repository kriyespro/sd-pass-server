from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import FileResponse, Http404, HttpResponseRedirect
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
        create_platform_backup_task.delay(backup.pk)
        messages.success(request, f'Backup started ({backup.get_backup_type_display()}).')
        return HttpResponseRedirect(reverse('admin_monitor:dashboard'))


class DownloadPlatformBackupView(StaffOnlyMixin, View):
    def get(self, request, backup_id: int):
        backup = get_object_or_404(
            PlatformBackup,
            pk=backup_id,
            status=PlatformBackup.Status.DONE,
        )
        try:
            from apps.platform_ops.services.backup import resolve_backup_path

            path = resolve_backup_path(backup)
        except (ValueError, FileNotFoundError):
            raise Http404('Backup file not found.')
        return FileResponse(
            path.open('rb'),
            as_attachment=True,
            filename=path.name,
        )
