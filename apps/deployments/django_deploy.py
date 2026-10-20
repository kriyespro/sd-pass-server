"""
Django app deployment pipeline.
Called from the Celery deploy task when project_type == DJANGO.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from apps.databases.services import database_url_for_instance, get_or_provision_postgres_db
from apps.deployments.flask_runtime import allocate_django_port, runner_deploy
from apps.deployments.python_zip_utils import extract_zip, validate_zip
from apps.deployments.services import project_site_dir
from apps.projects.models import Project

MAX_DJANGO_ZIP_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_DJANGO_FILES    = 500

# Mirrors flask_runner/runner.py's own detection — duplicated deliberately
# (a different process/container; same shared filesystem) so resolving
# MEDIA_ROOT below doesn't need a round trip through the runner's HTTP API.
_DJANGO_SETTINGS_RE = re.compile(
    r"""setdefault\(\s*['"]DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]\s*\)"""
)
# manage.py's hardcoded DJANGO_SETTINGS_MODULE default is very commonly a DEV
# settings module (config.settings.dev) — correct for local development, but
# this platform only ever runs in production. A dev settings module commonly
# hardcodes a local sqlite3 database (silently ignoring the Postgres
# DATABASE_URL this platform injects, so every redeploy wipes whatever was in
# that sqlite file since it isn't part of the git repo) and DEBUG=True. If a
# sibling prod/production module exists next to the detected one, prefer it —
# exactly like requirements/prod.txt is preferred over requirements/dev.txt
# elsewhere in this pipeline. Mirrors flask_runner/runner.py's own version of
# this same heuristic.
_DEV_SETTINGS_NAMES = frozenset({'dev', 'development', 'local', 'debug'})
_PROD_SETTINGS_CANDIDATES = ('prod', 'production', 'release')
_MEDIA_ROOT_SCRIPT = """
import django
django.setup()
from django.conf import settings
print(str(getattr(settings, 'MEDIA_ROOT', '') or ''))
"""
_MEDIA_PROBE_TIMEOUT = 30


def _prefer_production_settings(project_dir: Path, settings_module: str) -> str:
    parts = settings_module.split('.')
    if parts[-1].lower() not in _DEV_SETTINGS_NAMES:
        return settings_module
    settings_dir = project_dir.joinpath(*parts[:-1])
    for candidate in _PROD_SETTINGS_CANDIDATES:
        if (settings_dir / f'{candidate}.py').is_file():
            return '.'.join(parts[:-1] + [candidate])
    return settings_module


def _detect_settings_module(project_dir: Path) -> str | None:
    manage_py = project_dir / 'manage.py'
    if not manage_py.is_file():
        return None
    try:
        match = _DJANGO_SETTINGS_RE.search(manage_py.read_text(errors='ignore'))
    except OSError:
        return None
    if not match:
        return None
    return _prefer_production_settings(project_dir, match.group(1))


def _resolve_media_root(site_dir: Path, runner_env: dict[str, str]) -> Path | None:
    """
    Best-effort: ask the CURRENTLY deployed code (its own venv, its own
    settings) where it keeps user-uploaded files, so a redeploy can carry
    them over instead of silently deleting them along with the old code.
    Returns an absolute path if MEDIA_ROOT resolves to somewhere inside
    site_dir, else None (including on any failure — this is advisory, never
    allowed to block a deploy).
    """
    python = site_dir / '.venv' / 'bin' / 'python'
    settings_module = _detect_settings_module(site_dir)
    if not settings_module or not python.is_file():
        return None

    # Include the owner's own custom env vars too — some settings modules
    # (e.g. ones requiring REDIS_URL for a cache backend) raise at import
    # time without them, which would otherwise make this probe fail even
    # though it isn't actually about the database.
    env = {
        'PATH': '/usr/bin:/bin',
        'PYTHONPATH': str(site_dir),
        **runner_env,
        'DJANGO_SETTINGS_MODULE': settings_module,
    }
    try:
        r = subprocess.run(
            [str(python), '-c', _MEDIA_ROOT_SCRIPT],
            cwd=str(site_dir), env=env,
            capture_output=True, text=True, timeout=_MEDIA_PROBE_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None

    media_root = (r.stdout or '').strip()
    if not media_root:
        return None
    try:
        resolved = Path(media_root).resolve()
        if resolved.is_relative_to(site_dir.resolve()):
            return resolved
    except (OSError, ValueError):
        pass
    return None


def _rollback(site_dir: Path, previous_dir: Path) -> bool:
    """Swap a broken new deploy back out for the last-known-good version, if any."""
    if not previous_dir.exists():
        return False
    shutil.rmtree(site_dir, ignore_errors=True)
    shutil.move(str(previous_dir), str(site_dir))
    return True


def deploy_django_project(project: Project, zip_path: Path) -> tuple[bool, str]:
    """
    Full Django deploy pipeline:
    1. Validate ZIP
    2. Extract into a staging dir — the live site is never touched until the
       new ZIP is known to have extracted cleanly
    3. Carry over locally-stored user uploads (MEDIA_ROOT) and a copy of the
       existing venv from the currently-deployed code, if any
    4. Atomically swap the staging dir into place, keeping the previous
       version as a rollback point untouched on disk
    5. Allocate port, get/provision the project's Postgres database
    6. Call runner to install deps, migrate, and start gunicorn — rolling
       back to the previous working version (and restarting it) on failure
    7. Return (ok, message)

    The project's PostgreSQL database is never dropped or recreated here
    (get_or_provision_postgres_db reuses the existing instance), so existing
    data and user accounts are never affected by a redeploy/update — PROVIDED
    the app's settings module actually reads DATABASE_URL. If manage.py
    defaults to a dev-looking settings module (config.settings.dev) that
    hardcodes sqlite3 instead, _prefer_production_settings swaps in a sibling
    prod/production module when one exists, since a sqlite file living
    inside the extracted site dir would otherwise be silently wiped on every
    single redeploy (it isn't part of the git repo, so each fresh extraction
    starts with none).
    """
    # 1. Validate
    ok, err = validate_zip(
        zip_path,
        max_files=MAX_DJANGO_FILES,
        max_size=MAX_DJANGO_ZIP_SIZE,
    )
    if not ok:
        return False, err

    site_dir = project_site_dir(project)
    is_redeploy = site_dir.exists()

    # 2. Extract into a staging dir first.
    staging_dir = site_dir.parent / f'.staging_{project.pk}'
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        extract_zip(zip_path, staging_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False, f'ZIP extraction failed: {exc}'

    # Dedicated PostgreSQL database (created on first deploy, reused on
    # redeploys/updates — never dropped or recreated here).
    db_instance = get_or_provision_postgres_db(project)
    database_url = database_url_for_instance(db_instance)

    # The owner's own custom env vars (set on the project's Environment page)
    # — e.g. REDIS_URL for a prod settings module that needs a cache backend
    # this platform doesn't provision automatically. DATABASE_URL always
    # wins over a same-named custom var, since that one is platform-managed.
    from apps.envmanager.services import decrypted_env_for_project
    runner_env = {**decrypted_env_for_project(project), 'DATABASE_URL': database_url}

    if is_redeploy:
        # Carry over user-uploaded media so an update never deletes it.
        old_media_root = _resolve_media_root(site_dir, runner_env)
        if old_media_root and old_media_root.is_dir():
            rel = old_media_root.relative_to(site_dir.resolve())
            new_media_root = staging_dir / rel
            if new_media_root.exists():
                shutil.rmtree(new_media_root)
            new_media_root.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(old_media_root, new_media_root)

        # Copy (not move) the existing venv so the rollback copy below stays
        # untouched even if this redeploy's pip install mutates it.
        old_venv = site_dir / '.venv'
        if old_venv.is_dir():
            shutil.copytree(old_venv, staging_dir / '.venv', symlinks=False)

    # 3. Atomic swap: move the current site_dir aside as a rollback point
    #    (kept until the new version deploys successfully), then move the
    #    staging dir into place.
    previous_dir = site_dir.parent / f'.previous_{project.pk}'
    if is_redeploy:
        if previous_dir.exists():
            shutil.rmtree(previous_dir)
        shutil.move(str(site_dir), str(previous_dir))
    shutil.move(str(staging_dir), str(site_dir))

    # 4. Port
    try:
        port = allocate_django_port(project.pk)
    except RuntimeError as exc:
        _rollback(site_dir, previous_dir)
        return False, str(exc)

    # 5. Runner: install deps, migrate against Postgres, start gunicorn
    ok, result = runner_deploy(
        project.pk, port, project_type='django',
        env=runner_env,
    )
    if not ok:
        if _rollback(site_dir, previous_dir):
            runner_deploy(project.pk, port, project_type='django', env=runner_env)
            return False, f'Update failed and was rolled back to the previous working version: {result}'
        return False, f'Runner failed: {result}'

    if previous_dir.exists():
        shutil.rmtree(previous_dir, ignore_errors=True)

    settings_module = _detect_settings_module(site_dir) or '?'
    return True, f'Django app started on port {port} (entry: {result}, settings: {settings_module})'
