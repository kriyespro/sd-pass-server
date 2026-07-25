from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.containers.services import container_name, container_stats
from apps.databases.models import DatabaseInstance
from apps.domains.services import site_url_for
from apps.projects.models import Project, ProjectType

from .models import DrupalInstance


class ProjectDrupalView(LoginRequiredMixin, View):
    template_name = 'pages/drupal/project_drupal.jinja'

    def dispatch(self, request, *args, **kwargs):
        self.project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
            project_type=ProjectType.DRUPAL,
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        drupal_instance = DrupalInstance.objects.filter(project=self.project).first()
        db = DatabaseInstance.objects.filter(
            project=self.project, engine=DatabaseInstance.Engine.MYSQL,
        ).first()
        stats = container_stats(container_name(self.project))
        return render(
            request,
            self.template_name,
            {
                'project': self.project,
                'drupal_instance': drupal_instance,
                'db': db,
                'site_url': site_url_for(self.project),
                'is_running': stats.get('status') == 'running',
                'stats': stats,
            },
        )


class ProjectDrupalDbRevealView(LoginRequiredMixin, View):
    """HTMX POST — decrypts and returns the MySQL password as an HTML partial
    (never embedded in the initial page render). See php.txt section 7."""
    http_method_names = ['post']
    template_name = 'partials/drupal/_db_password.jinja'

    def post(self, request, *args, **kwargs):
        from cryptography.fernet import Fernet
        from django.conf import settings

        project = get_object_or_404(
            Project,
            slug=kwargs['slug'],
            owner=request.user,
            is_deleted=False,
            project_type=ProjectType.DRUPAL,
        )
        db = get_object_or_404(
            DatabaseInstance, project=project, engine=DatabaseInstance.Engine.MYSQL,
        )
        password = Fernet(settings.FERNET_KEY).decrypt(db.password_encrypted.encode()).decode()
        return render(request, self.template_name, {'password': password})
