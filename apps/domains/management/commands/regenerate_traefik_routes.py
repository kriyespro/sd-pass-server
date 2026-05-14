from django.core.management.base import BaseCommand

from apps.domains.services import write_project_router_file
from apps.projects.models import Project


class Command(BaseCommand):
    help = 'Rewrite Traefik file-provider YAML for every non-deleted project (uses current TRAEFIK_* settings).'

    def handle(self, *args, **options):
        n = 0
        for project in Project.objects.filter(is_deleted=False).iterator():
            path, fqdn = write_project_router_file(project)
            extra = getattr(project, 'custom_hostname', None) or ''
            if extra:
                self.stdout.write(f'{project.subdomain} -> {path} ({fqdn}, also Host(`{extra}`))')
            else:
                self.stdout.write(f'{project.subdomain} -> {path} ({fqdn})')
            n += 1
        self.stdout.write(self.style.SUCCESS(f'Wrote {n} route file(s).'))
