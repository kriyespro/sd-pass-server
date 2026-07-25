"""
WordPress provisioning (php.txt section 4 / section 9 Phase 2). Same shape as
GOAL.md's Feature 1, adjusted to call apps.containers.services (containers_runner
sidecar) instead of the docker SDK directly, and apps.containers.mysql.create_mysql_db
for a per-project MySQL container instead of a shared instance (php.txt section 10,
decision 3).
"""
from __future__ import annotations

import secrets
import string
import time

from cryptography.fernet import Fernet
from django.conf import settings

from apps.containers.mysql import create_mysql_db, drop_mysql_db
from apps.containers.services import (
    container_name,
    exec_in_container,
    mysql_container_name,
    remove_container,
    start_container,
    stop_container,
)
from apps.databases.models import DatabaseInstance
from apps.domains.services import remove_project_router_file, site_url_for, write_project_router_file
from apps.logs.models import LogKind
from apps.logs.services import append_project_log
from apps.projects.models import Project, ProjectStatus

from .models import WordPressInstance

WORDPRESS_IMAGE = 'wordpress:apache'

# wp-cli.phar is fetched at first-boot (not baked into the official wordpress:apache
# image) so a host with no outbound internet just skips unattended install — the site
# still comes up and the visitor completes WordPress's own /wp-admin/install.php wizard.
_WP_CLI_FETCH_CMD = [
    'php', '-r',
    "copy('https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar', '/usr/local/bin/wp');",
]
_WP_CLI_CHMOD_CMD = ['chmod', '+x', '/usr/local/bin/wp']


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _encrypt(value: str) -> str:
    return Fernet(settings.FERNET_KEY).encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return Fernet(settings.FERNET_KEY).decrypt(value.encode()).decode()


def _wait_for_mysql(name: str, attempts: int = 15, delay: float = 2.0) -> bool:
    """Poll the per-project MySQL container until it answers, before running wp-cli."""
    for _ in range(attempts):
        ok, _ = exec_in_container(name, ['mysqladmin', 'ping', '-h', 'localhost'], timeout=10)
        if ok:
            return True
        time.sleep(delay)
    return False


def provision(project: Project, admin_email: str) -> WordPressInstance:
    """
    1. create_mysql_db(project)            → per-project mysql:8 container
    2. docker run wordpress:apache         → app container on platform_net
    3. write_project_router_file(project)  → Traefik → proj_<id>:80
    4. best-effort wp-cli unattended install so the site is usable immediately
    5. project.status = RUNNING
    """
    from apps.billing.services import docker_limits_for_project

    db = create_mysql_db(project)
    app_name = container_name(project)
    limits = docker_limits_for_project(project)['app']

    admin_user = 'admin'
    admin_pass = _generate_password()

    ok, msg = start_container(
        app_name,
        image=WORDPRESS_IMAGE,
        env={
            'WORDPRESS_DB_HOST': f"{db['host']}:3306",
            'WORDPRESS_DB_NAME': db['db'],
            'WORDPRESS_DB_USER': db['user'],
            'WORDPRESS_DB_PASSWORD': db['password'],
            'WORDPRESS_TABLE_PREFIX': 'wp_',
        },
        volumes={'data': '/var/www/html'},
        mem_limit=limits['mem_limit'],
        nano_cpus=limits['nano_cpus'],
    )
    if not ok:
        drop_mysql_db(project)
        raise RuntimeError(f'WordPress container provisioning failed for {app_name}: {msg}')

    write_project_router_file(project)

    wp, _ = WordPressInstance.objects.update_or_create(
        project=project,
        defaults={
            'container_id': app_name,
            'wp_admin_user': admin_user,
            'wp_admin_pass_enc': _encrypt(admin_pass),
            'wp_admin_email': admin_email,
        },
    )

    if _wait_for_mysql(mysql_container_name(project)):
        fetched_ok, _out = exec_in_container(app_name, _WP_CLI_FETCH_CMD, timeout=60)
        if fetched_ok:
            exec_in_container(app_name, _WP_CLI_CHMOD_CMD, timeout=10)
            exec_in_container(
                app_name,
                [
                    'wp', 'core', 'install',
                    '--path=/var/www/html',
                    f'--url={site_url_for(project)}',
                    f'--title={project.name}',
                    f'--admin_user={admin_user}',
                    f'--admin_password={admin_pass}',
                    f'--admin_email={admin_email}',
                    '--skip-email',
                    '--allow-root',
                ],
                timeout=60,
            )
        else:
            append_project_log(
                project, LogKind.SYSTEM,
                'wp-cli unattended install unavailable (no internet egress?) — '
                'complete setup at /wp-admin/install.php using the site URL.',
            )
    else:
        append_project_log(project, LogKind.SYSTEM, 'MySQL did not become ready in time for wp-cli install.')

    Project.objects.filter(pk=project.pk).update(status=ProjectStatus.RUNNING)
    return wp


def deprovision(project: Project) -> None:
    """Stop + remove the app container (with its volume), drop the MySQL container/DB,
    remove the Traefik route, and forget the WordPressInstance row."""
    app_name = container_name(project)
    stop_container(app_name)
    remove_container(app_name, remove_volumes=True)
    drop_mysql_db(project)
    remove_project_router_file(project)
    WordPressInstance.objects.filter(project=project).delete()


def reset_admin_password(project: Project) -> tuple[bool, str]:
    """
    Generate a new admin password and write it directly into wp_users via the
    project's own MySQL container — wp-cli is best-effort at provision time and may
    not be present (see provision()). WordPress accepts legacy MD5 password hashes
    for verification and rehashes them on the next successful login.
    """
    try:
        wp = project.wordpress_instance
    except WordPressInstance.DoesNotExist:
        return False, 'No WordPress instance for this project.'

    db = DatabaseInstance.objects.filter(project=project, engine=DatabaseInstance.Engine.MYSQL).first()
    if db is None:
        return False, 'No database instance found for this project.'

    new_pass = _generate_password()
    db_pass = _decrypt(db.password_encrypted)
    sql = (
        f"UPDATE wp_users SET user_pass = MD5('{new_pass}') "
        f"WHERE user_login = '{wp.wp_admin_user}';"
    )
    ok, output = exec_in_container(
        mysql_container_name(project),
        ['mysql', '-u', db.username, f'-p{db_pass}', db.name, '-e', sql],
        timeout=30,
    )
    if not ok:
        return False, output or 'Password reset failed.'

    wp.wp_admin_pass_enc = _encrypt(new_pass)
    wp.save(update_fields=['wp_admin_pass_enc', 'updated_at'])
    return True, new_pass
