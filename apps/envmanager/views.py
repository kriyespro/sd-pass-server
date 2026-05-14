from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView

from apps.projects.models import Project

from .forms import EnvVarForm
from .models import EnvVar


class ProjectEnvironmentView(LoginRequiredMixin, CreateView):
    model = EnvVar
    form_class = EnvVarForm
    template_name = 'pages/env/project_environment.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['project'] = self.project
        ctx['env_vars'] = EnvVar.objects.filter(project=self.project).order_by('key')
        return ctx

    def form_valid(self, form):
        form.instance.project = self.project
        try:
            response = super().form_valid(form)
        except IntegrityError:
            form.add_error('key', 'This variable name is already used for this project.')
            return self.form_invalid(form)
        messages.success(self.request, f'Environment variable “{form.instance.key}” saved.')
        return response

    def get_success_url(self):
        return reverse_lazy('projects:environment', kwargs={'slug': self.project.slug})
