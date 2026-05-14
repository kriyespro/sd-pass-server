from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views.generic import ListView

from apps.projects.models import Project
from core.mixins import SafePaginationMixin

from .models import LogEntry


class ProjectLogsView(LoginRequiredMixin, SafePaginationMixin, ListView):
    model = LogEntry
    template_name = 'pages/logs/project_logs.jinja'
    context_object_name = 'log_entries'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return LogEntry.objects.filter(project=self.project).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        return ctx


class ProjectLogsTablePartialView(LoginRequiredMixin, SafePaginationMixin, ListView):
    """HTMX target: refreshed log table without full page."""
    model = LogEntry
    template_name = 'partials/logs/_log_table.jinja'
    context_object_name = 'log_entries'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return LogEntry.objects.filter(project=self.project).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        return ctx
