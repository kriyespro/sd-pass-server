"""Create/reset a Django superuser account directly in a deployed project's own database."""
from __future__ import annotations

from apps.databases.models import DatabaseInstance
from apps.databases.services import database_url_for_instance
from apps.deployments.flask_runtime import runner_set_django_superuser
from apps.projects.models import Project


def set_django_superuser(project: Project, username: str, email: str, password: str) -> tuple[bool, str]:
    """Returns (True, 'created'|'updated') or (False, error_message)."""
    db_instance = DatabaseInstance.objects.filter(
        project=project, engine=DatabaseInstance.Engine.POSTGRES,
    ).first()
    if not db_instance:
        return False, 'This project has not deployed successfully yet — deploy it once first.'

    database_url = database_url_for_instance(db_instance)
    return runner_set_django_superuser(
        project.pk, username, email, password, env={'DATABASE_URL': database_url},
    )
