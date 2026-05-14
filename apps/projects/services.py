"""Project lifecycle helpers (delete, etc.)."""
from __future__ import annotations

import shutil
import uuid

from django.db import transaction

from apps.backups.models import BackupJob
from apps.databases.models import DatabaseInstance
from apps.deployments.models import Deployment
from apps.deployments.services import delete_runtime_env_snapshot, project_site_dir
from apps.dnsmanager.models import DnsRecord
from apps.domains.models import ProjectRoute
from apps.domains.services import remove_project_router_file
from apps.envmanager.models import EnvVar
from apps.logs.models import LogEntry
from apps.projects.host_allowlist import invalidate_custom_host_cache
from apps.projects.models import Project, ProjectStatus
from apps.uploads.models import ProjectUpload


def _tombstone_field(value: str, suffix: str, max_len: int) -> str:
    combined = f'{value}{suffix}'
    if len(combined) <= max_len:
        return combined
    return f'{value[: max(0, max_len - len(suffix))]}{suffix}'[:max_len]


def soft_delete_project(*, project: Project, user) -> tuple[bool, str]:
    """
    Mark project deleted for the owner, remove published site files and related rows,
    drop Traefik route file, and rename slug/subdomain so names can be reused.
    """
    if project.owner_id != user.id:
        return False, 'forbidden'
    if project.is_deleted:
        return False, 'already_deleted'

    suffix = f'-del-{uuid.uuid4().hex[:12]}'

    with transaction.atomic():
        locked = (
            Project.objects.select_for_update()
            .filter(pk=project.pk, owner_id=user.id, is_deleted=False)
            .first()
        )
        if locked is None:
            return False, 'already_deleted'

        invalidate_custom_host_cache(locked.custom_hostname)

        remove_project_router_file(locked)
        ProjectRoute.objects.filter(project=locked).delete()
        DnsRecord.objects.filter(project=locked).delete()
        BackupJob.objects.filter(project=locked).delete()
        DatabaseInstance.objects.filter(project=locked).delete()
        EnvVar.objects.filter(project=locked).delete()
        LogEntry.objects.filter(project=locked).delete()
        Deployment.objects.filter(project=locked).delete()

        for upl in list(ProjectUpload.objects.filter(project=locked)):
            try:
                upl.file.delete(save=False)
            except OSError:
                pass
            upl.delete()

        site = project_site_dir(locked)
        if site.exists():
            shutil.rmtree(site, ignore_errors=True)

        delete_runtime_env_snapshot(locked)

        new_slug = _tombstone_field(locked.slug, suffix, 200)
        new_sub = _tombstone_field(locked.subdomain, suffix, 200)

        Project.objects.filter(pk=locked.pk).update(
            is_deleted=True,
            status=ProjectStatus.STOPPED,
            slug=new_slug,
            subdomain=new_sub,
            custom_hostname=None,
            custom_hostname_verified=False,
            custom_domain_challenge_token='',
        )

    return True, ''
