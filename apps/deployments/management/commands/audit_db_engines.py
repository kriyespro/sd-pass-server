"""Report which database engine every deployed Django project is actually using."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.deployments.flask_runtime import runner_audit_db_engines
from apps.projects.models import Project, ProjectType


class Command(BaseCommand):
    help = (
        'For every Django project, report the database engine its own settings.py '
        'actually resolved to at runtime -- catches projects whose settings.py '
        'ignores the platform-injected DATABASE_URL and silently falls back to '
        'sqlite3 (which loses all data on every redeploy).'
    )

    def handle(self, *args, **options):
        report = runner_audit_db_engines()
        if not report:
            self.stdout.write(self.style.ERROR(
                'No data — flask-runner unreachable, or no Django projects known to it.'
            ))
            return

        projects = {
            p.pk: p
            for p in Project.objects.filter(
                pk__in=[int(k) for k in report], project_type=ProjectType.DJANGO,
            )
        }

        bad, ok = [], []
        for pid_str, info in report.items():
            project = projects.get(int(pid_str))
            label = f'{project.slug} (id={pid_str})' if project else f'id={pid_str}'
            if 'error' in info:
                bad.append(f'{label}: ERROR — {info["error"]}')
            elif info.get('is_postgres'):
                ok.append(f'{label}: postgres — {info.get("host")}/{info.get("name")}')
            else:
                bad.append(f'{label}: NOT POSTGRES — engine={info.get("engine") or "(unknown)"}')

        if ok:
            self.stdout.write(self.style.SUCCESS(f'\n✅ On PostgreSQL ({len(ok)}):'))
            for line in ok:
                self.stdout.write(f'  {line}')

        if bad:
            self.stdout.write(self.style.ERROR(f'\n❌ NOT on PostgreSQL / errored ({len(bad)}):'))
            for line in bad:
                self.stdout.write(f'  {line}')
        else:
            self.stdout.write(self.style.SUCCESS('\nAll Django projects are on PostgreSQL.'))
