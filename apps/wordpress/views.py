from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from apps.containers.services import container_name, container_stats
from apps.databases.models import DatabaseInstance
from apps.projects.models import Project, ProjectType

from .models import WordPressInstance
from .services import site_url_for


class ProjectWordPressView(LoginRequiredMixin, View):
    template_name = 'pages/wordpress/project_wordpress.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
            project_type=ProjectType.WORDPRESS,
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        wp_instance = WordPressInstance.objects.filter(project=self.project).first()
        db = DatabaseInstance.objects.filter(
            project=self.project, engine=DatabaseInstance.Engine.MYSQL,
        ).first()
        stats = container_stats(container_name(self.project))
        return render(
            request,
            self.template_name,
            {
                'project': self.project,
                'wp_instance': wp_instance,
                'db': db,
                'site_url': site_url_for(self.project),
                'stats': stats,
            },
        )


class ProjectWordPressResetPasswordView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        from .services import reset_admin_password

        project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
            project_type=ProjectType.WORDPRESS,
        )
        ok, result = reset_admin_password(project)
        if ok:
            messages.success(
                request,
                f'Admin password reset. New password (copy it now, shown only once): {result}',
            )
        else:
            messages.error(request, f'Password reset failed: {result}')
        return HttpResponseRedirect(reverse('projects:wordpress', kwargs={'slug': project.slug}))
