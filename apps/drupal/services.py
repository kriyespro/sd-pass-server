"""
Drupal provisioning (php.txt section 6 / section 9 Phase 4). Structurally identical
to generic PHP (apps/phpapps/services.py) — same shared php-runtime image, same
per-project MySQL provisioner, same named-volume-per-project + put_archive upload
mechanism (see phpapps/services.py's module docstring for why: prod's sites_data is a
named Docker volume, not a host path containers_runner could bind-mount). Reuses
phpapps's safe-unzip/tar-build mechanics directly rather than a third copy. Differs by:
  - fixed document root (/var/www/html/web, Drupal's composer.json-managed layout)
  - two provisioning entry paths: upload an existing Drupal codebase, or scaffold a
    fresh one with `composer create-project drupal/recommended-project`
  - a first-boot `drush site:install` step when sites/default/settings.php is absent
"""
from __future__ import annotations

import secrets
import shutil
import string
import tempfile
import zipfile
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings

from apps.containers.mysql import create_mysql_db, drop_mysql_db
from apps.containers.services import (
    container_name,
    exec_in_container,
    remove_container,
    start_container,
    stop_container,
    upload_archive,
)
from apps.domains.services import remove_project_router_file, write_project_router_file
from apps.phpapps.services import _build_tar, _extract_php_zip_to, _is_ignored_entry
from apps.projects.models import Project, ProjectStatus

from .models import DrupalInstance

DRUPAL_IMAGE = 'sd-pass/php-runtime:latest'  # same shared image as generic PHP, see php.txt 5.1
DRUPAL_DOCROOT = '/var/www/html/web'

DRUPAL_ALLOWED_SUFFIXES = frozenset({
    '.php', '.module', '.install', '.theme', '.inc', '.engine', '.profile',
    '.yml', '.twig', '.po',
    '.html', '.htm', '.css', '.js', '.mjs', '.json',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.txt', '.md',
    '.cfg', '.ini', '.toml', '.yaml',
    '.csv', '.xml', '.sql',
})
DRUPAL_ALLOWED_FILENAMES = frozenset({'composer.json', 'composer.lock', '.env.example', '.htaccess'})

# Drupal codebases with contrib modules/vendor run larger than plain PHP.
MAX_DRUPAL_ZIP_SIZE = 150 * 1024 * 1024
MAX_DRUPAL_FILES = 8000


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _encrypt(value: str) -> str:
    return Fernet(settings.FERNET_KEY).encrypt(value.encode()).decode()


def _validate_drupal_zip(zip_path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]
            real_entries = [
                i for i in entries
                if not _is_ignored_entry((i.filename or '').replace('\\', '/').strip())
            ]
            if len(real_entries) > MAX_DRUPAL_FILES:
                return False, f'ZIP contains {len(real_entries)} files (max {MAX_DRUPAL_FILES})'
            total = 0
            for info in real_entries:
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or name.startswith('/') or '..' in name.split('/'):
                    return False, f'Unsafe ZIP entry: {name!r}'
                base = Path(name).name.lower()
                suf = Path(name).suffix.lower()
                if suf not in DRUPAL_ALLOWED_SUFFIXES and base not in DRUPAL_ALLOWED_FILENAMES:
                    return False, f'File type not allowed: {name!r}.'
                total += info.file_size
                if total > MAX_DRUPAL_ZIP_SIZE:
                    return False, f'ZIP contents exceed {MAX_DRUPAL_ZIP_SIZE // 1024 // 1024} MB limit'
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)
    return True, ''


def extract_drupal_zip(zip_path: Path) -> tuple[bool, str, Path | None]:
    """Validate + extract into a fresh temp dir. Caller owns the returned dir and
    must shutil.rmtree() it when done."""
    ok, err = _validate_drupal_zip(zip_path)
    if not ok:
        return False, err, None

    tmp_dir = Path(tempfile.mkdtemp(prefix='drupal_deploy_'))
    try:
        _extract_php_zip_to(zip_path, tmp_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False, f'ZIP extraction failed: {exc}', None
    return True, 'extracted_ok', tmp_dir


def site_needs_install(site_dir: Path) -> bool:
    return not (site_dir / 'web' / 'sites' / 'default' / 'settings.php').is_file()


def _run_site_install(app_name: str, db: dict, admin_pass: str, site_name: str) -> tuple[bool, str]:
    db_url = f"mysql://{db['user']}:{db['password']}@{db['host']}:3306/{db['db']}"
    return exec_in_container(
        app_name,
        [
            'drush', 'site:install', 'standard',
            f'--root={DRUPAL_DOCROOT}',
            f'--db-url={db_url}',
            '--account-name=admin',
            f'--account-pass={admin_pass}',
            f'--site-name={site_name}',
            '-y',
        ],
        timeout=180,
    )


def provision(project: Project, zip_path: Path | None, admin_email: str) -> DrupalInstance:
    """
    1. create_mysql_db(project).
    2. Recreate the app container (named volume `proj_<id>_data`, reused across
       redeploys since removing a container doesn't remove its named volume).
    3a. Upload path (zip_path given): wipe + upload the extracted ZIP's files,
        composer install if composer.json is present.
    3b. Scaffold path (zip_path is None): `composer create-project
        drupal/recommended-project` directly into the (empty) volume — same
        no-ZIP-needed UX as WordPress.
    4. First boot only (sites/default/settings.php absent): `drush site:install`,
       storing the generated admin password encrypted. If the upload already had its
       own settings.php, the platform never learns its password (left blank).
    5. write_project_router_file(project); project.status = RUNNING.
    """
    from apps.billing.services import docker_limits_for_project

    site_dir: Path | None = None
    if zip_path is not None:
        ok, msg, site_dir = extract_drupal_zip(zip_path)
        if not ok:
            raise RuntimeError(msg)

    try:
        db = create_mysql_db(project)
        app_name = container_name(project)
        limits = docker_limits_for_project(project)['app']

        started_ok, started_msg = start_container(
            app_name,
            image=DRUPAL_IMAGE,
            env={'APACHE_DOCUMENT_ROOT': DRUPAL_DOCROOT},
            volumes={'data': '/var/www/html'},
            mem_limit=limits['mem_limit'],
            nano_cpus=limits['nano_cpus'],
        )
        if not started_ok:
            drop_mysql_db(project)
            raise RuntimeError(f'Drupal container provisioning failed for {app_name}: {started_msg}')

        if site_dir is not None:
            # Clears the previous build's files on a redeploy; no-op on first
            # deploy (fresh empty volume).
            exec_in_container(app_name, ['find', '/var/www/html', '-mindepth', '1', '-delete'], timeout=30)
            tar_bytes = _build_tar(site_dir)
            up_ok, up_msg = upload_archive(app_name, tar_bytes, dest_path='/var/www/html')
            if not up_ok:
                raise RuntimeError(f'Uploading site files failed: {up_msg}')
            if (site_dir / 'composer.json').is_file():
                exec_in_container(
                    app_name,
                    ['composer', 'install', '--no-dev', '--no-interaction', '--working-dir=/var/www/html'],
                    timeout=300,
                )
            needs_install = site_needs_install(site_dir)
        else:
            scaffold_ok, scaffold_out = exec_in_container(
                app_name,
                ['composer', 'create-project', 'drupal/recommended-project', '/var/www/html', '--no-interaction'],
                timeout=600,
            )
            if not scaffold_ok:
                raise RuntimeError(f'Drupal scaffold failed: {scaffold_out}')
            needs_install = True

        existing = DrupalInstance.objects.filter(project=project).first()
        if needs_install:
            admin_pass = _generate_password()
            install_ok, install_out = _run_site_install(app_name, db, admin_pass, project.name)
            if not install_ok:
                raise RuntimeError(f'drush site:install failed: {install_out}')
            admin_pass_enc = _encrypt(admin_pass)
        else:
            admin_pass_enc = existing.admin_pass_enc if existing else ''

        drupal, _ = DrupalInstance.objects.update_or_create(
            project=project,
            defaults={
                'container_id': app_name,
                'admin_user': 'admin',
                'admin_pass_enc': admin_pass_enc,
                'admin_email': admin_email,
                'site_name': project.name,
            },
        )

        write_project_router_file(project)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.RUNNING)
        return drupal
    finally:
        if site_dir is not None:
            shutil.rmtree(site_dir, ignore_errors=True)


def deprovision(project: Project) -> None:
    """Stop + remove the app container (with its volume), drop the MySQL container/DB,
    remove the Traefik route, and forget the DrupalInstance row."""
    app_name = container_name(project)
    stop_container(app_name)
    remove_container(app_name, remove_volumes=True)
    drop_mysql_db(project)
    remove_project_router_file(project)
    DrupalInstance.objects.filter(project=project).delete()
