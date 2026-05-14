from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views.generic import ListView

from apps.backups.models import BackupJob
from apps.projects.models import Project


class ProjectBackupsView(LoginRequiredMixin, ListView):
    model = BackupJob
    template_name = 'pages/backups/project_backups.jinja'
    context_object_name = 'backup_jobs'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return BackupJob.objects.filter(project=self.project).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        return ctx
