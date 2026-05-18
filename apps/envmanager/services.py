"""Env helpers for deploy/runtime (values never logged in plain text)."""

from __future__ import annotations

from apps.envmanager.models import EnvVar
from apps.projects.models import Project


def decrypted_env_for_project(project: Project) -> dict[str, str]:
    """Return env key → plaintext value for injection at deploy/runtime."""
    from cryptography.fernet import Fernet
    from django.conf import settings

    f = Fernet(settings.FERNET_KEY)
    out: dict[str, str] = {}
    for ev in EnvVar.objects.filter(project=project).order_by('key'):
        out[ev.key] = f.decrypt(ev.value_ciphertext.encode()).decode()
    return out
