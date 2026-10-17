"""Create/reset a Django superuser account directly in a deployed project's own database."""
from __future__ import annotations

import secrets

from django.conf import settings

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


def _encrypt(value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(settings.FERNET_KEY).encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(settings.FERNET_KEY).decrypt(value.encode()).decode()


def _generated_superadmin_email(project: Project) -> str:
    """An email-shaped identifier derived from the app's own slug — used as
    both the account's email and its login identifier (see set_django_superuser
    callers), which is what actually makes login work on projects where
    email doubles as the username."""
    return f'admin@{project.slug}.local'


def ensure_django_superadmin(project: Project):
    """
    Auto-provision a Django superadmin the first time this project deploys
    successfully. Idempotent — a no-op on every later redeploy, since the
    credential record (and the account itself, in the project's database)
    already exists. Returns the DjangoSuperadmin row, or raises RuntimeError
    if the runner call failed.
    """
    from apps.deployments.models import DjangoSuperadmin

    existing = DjangoSuperadmin.objects.filter(project=project).first()
    if existing:
        return existing

    email = _generated_superadmin_email(project)
    password = secrets.token_urlsafe(12)
    ok, result = set_django_superuser(project, email, email, password)
    if not ok:
        raise RuntimeError(result)

    return DjangoSuperadmin.objects.create(
        project=project, email=email, password_encrypted=_encrypt(password),
    )


def regenerate_django_superadmin_password(project: Project) -> tuple[bool, str]:
    """Generate a brand-new random password for the project's superadmin
    (auto-provisioning it first if it somehow doesn't exist yet) and write
    it into the project's own database. Returns (True, 'created'|'updated')
    or (False, error_message)."""
    from apps.deployments.models import DjangoSuperadmin

    record = DjangoSuperadmin.objects.filter(project=project).first()
    email = record.email if record else _generated_superadmin_email(project)
    password = secrets.token_urlsafe(12)

    ok, result = set_django_superuser(project, email, email, password)
    if not ok:
        return False, result

    DjangoSuperadmin.objects.update_or_create(
        project=project, defaults={'email': email, 'password_encrypted': _encrypt(password)},
    )
    return True, result


def superadmin_credentials(project: Project) -> tuple[str, str] | None:
    """Return (email, plaintext_password) for display in Mission Control, or
    None if this project has no auto-provisioned superadmin yet."""
    from apps.deployments.models import DjangoSuperadmin

    record = DjangoSuperadmin.objects.filter(project=project).first()
    if not record:
        return None
    return record.email, _decrypt(record.password_encrypted)
