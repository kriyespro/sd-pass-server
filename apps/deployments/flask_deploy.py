"""
Flask app deployment pipeline.
Called from the Celery deploy task when project_type == FLASK.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from apps.deployments.flask_runtime import allocate_flask_port, runner_deploy
from apps.deployments.python_zip_utils import extract_zip, validate_zip
from apps.deployments.services import project_site_dir
from apps.projects.models import Project

# File extensions allowed inside a Flask project ZIP
FLASK_ALLOWED_SUFFIXES = frozenset({
    # Python
    '.py', '.pyw',
    # Templates / static
    '.html', '.htm', '.jinja', '.jinja2', '.j2', '.css', '.js', '.mjs', '.json',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    # Data / config
    '.sqlite', '.db',
    # Common document content apps legitimately store/serve (e.g. uploaded
    # client documents, certificates) — not executable, no reason to block.
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.txt', '.md',
    '.env', '.cfg', '.ini', '.toml', '.yaml', '.yml',
    '.csv', '.xml',
})

# Exact filenames allowed even though Path.suffix only sees their last dot
# (e.g. '.env.example' → suffix '.example', which isn't in FLASK_ALLOWED_SUFFIXES).
FLASK_ALLOWED_FILENAMES = frozenset({
    '.env.example', '.env.sample', '.env.local', '.env.development',
    '.env.production', '.env.test', '.gitignore', '.flaskenv',
})

MAX_FLASK_ZIP_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_FLASK_FILES    = 500


def deploy_flask_project(project: Project, zip_path: Path) -> tuple[bool, str]:
    """
    Full Flask deploy pipeline:
    1. Validate ZIP
    2. Extract files to project site dir
    3. Allocate port
    4. Call runner to install deps + start gunicorn
    5. Return (ok, message)
    """
    # 1. Validate
    ok, err = validate_zip(
        zip_path,
        allowed_suffixes=FLASK_ALLOWED_SUFFIXES,
        allowed_filenames=FLASK_ALLOWED_FILENAMES,
        max_files=MAX_FLASK_FILES,
        max_size=MAX_FLASK_ZIP_SIZE,
    )
    if not ok:
        return False, err

    # 2. Extract (wipe existing files first so stale .pyc etc. don't linger)
    site_dir = project_site_dir(project)
    # Keep .venv intact to avoid reinstalling everything on every deploy
    venv_backup: Path | None = None
    venv_dir = site_dir / '.venv'
    if venv_dir.exists():
        venv_backup = site_dir.parent / f'.venv_backup_{project.pk}'
        shutil.move(str(venv_dir), str(venv_backup))

    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)

    if venv_backup and venv_backup.exists():
        shutil.move(str(venv_backup), str(venv_dir))

    try:
        extract_zip(zip_path, site_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return False, f'ZIP extraction failed: {exc}'

    # 3. Port
    try:
        port = allocate_flask_port(project.pk)
    except RuntimeError as exc:
        return False, str(exc)

    # 4. Runner: install deps + start gunicorn
    ok, result = runner_deploy(project.pk, port)
    if not ok:
        return False, f'Runner failed: {result}'

    return True, f'Flask app started on port {port} (entry: {result})'
