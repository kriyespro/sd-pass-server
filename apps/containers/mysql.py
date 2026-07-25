"""
Per-project MySQL container provisioning (php.txt section 3, INF-5). One mysql:8
container per project — not a shared instance, see php.txt section 10 decision 3.
Writes into apps.databases.models.DatabaseInstance (Engine.MYSQL) rather than a
dedicated model.
"""
from __future__ import annotations

import secrets
import string

from cryptography.fernet import Fernet
from django.conf import settings

from apps.containers.services import mysql_container_name, remove_container, start_container, stop_container
from apps.databases.models import DatabaseInstance

MYSQL_IMAGE = 'mysql:8'


def _generate_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _encrypt(value: str) -> str:
    return Fernet(settings.FERNET_KEY).encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return Fernet(settings.FERNET_KEY).decrypt(value.encode()).decode()


def create_mysql_db(project) -> dict:
    """
    Provision a dedicated mysql:8 container for this project: one database, one
    non-root user with full privileges on it (MYSQL_RANDOM_ROOT_PASSWORD — nothing
    needs root). Returns {db, user, password, host}.
    """
    from apps.billing.services import docker_limits_for_project

    name = mysql_container_name(project)
    db_name = f'proj_{project.pk}'
    db_user = f'proj_{project.pk}'
    password = _generate_password()
    limits = docker_limits_for_project(project)['mysql']

    ok, msg = start_container(
        name,
        image=MYSQL_IMAGE,
        env={
            'MYSQL_DATABASE': db_name,
            'MYSQL_USER': db_user,
            'MYSQL_PASSWORD': password,
            'MYSQL_RANDOM_ROOT_PASSWORD': 'yes',
        },
        volumes={f'{name}_data': '/var/lib/mysql'},
        mem_limit=limits['mem_limit'],
        nano_cpus=limits['nano_cpus'],
    )
    if not ok:
        raise RuntimeError(f'MySQL container provisioning failed for {name}: {msg}')

    DatabaseInstance.objects.update_or_create(
        project=project,
        name=db_name,
        defaults={
            'engine': DatabaseInstance.Engine.MYSQL,
            'host': name,
            'port': 3306,
            'username': db_user,
            'password_encrypted': _encrypt(password),
        },
    )
    return {'db': db_name, 'user': db_user, 'password': password, 'host': name}


def drop_mysql_db(project) -> None:
    """Stop + remove this project's MySQL container (and its volume) and forget its credentials row."""
    name = mysql_container_name(project)
    stop_container(name)
    remove_container(name, remove_volumes=True)
    DatabaseInstance.objects.filter(project=project, engine=DatabaseInstance.Engine.MYSQL).delete()
