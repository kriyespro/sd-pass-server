"""
Flask app deployment pipeline.
Called from the Celery deploy task when project_type == FLASK.
"""
from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path

from django.conf import settings

from apps.deployments.flask_runtime import allocate_flask_port, runner_deploy
from apps.deployments.services import project_site_dir
from apps.logs.models import LogKind
from apps.logs.services import append_project_log
from apps.projects.models import Project

# File extensions allowed inside a Flask project ZIP
FLASK_ALLOWED_SUFFIXES = frozenset({
    # Python
    '.py', '.pyw',
    # Templates / static
    '.html', '.htm', '.css', '.js', '.mjs', '.json',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    # Data / config
    '.sqlite', '.db',
    '.txt', '.md',
    '.env', '.cfg', '.ini', '.toml', '.yaml', '.yml',
    '.csv', '.xml',
})

MAX_FLASK_ZIP_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_FLASK_FILES    = 500


def _validate_flask_zip(zip_path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]
            if len(entries) > MAX_FLASK_FILES:
                return False, f'ZIP contains {len(entries)} files (max {MAX_FLASK_FILES})'
            total = 0
            for info in entries:
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or name.startswith('/') or '..' in name.split('/'):
                    return False, f'Unsafe ZIP entry: {name!r}'
                suf = Path(name).suffix.lower()
                if suf and suf not in FLASK_ALLOWED_SUFFIXES:
                    return False, (
                        f'File type not allowed: {name!r}. '
                        f'Allowed: Python, HTML, CSS, JS, SQLite, images, config files.'
                    )
                total += info.file_size
                if total > MAX_FLASK_ZIP_SIZE:
                    return False, f'ZIP contents exceed {MAX_FLASK_ZIP_SIZE // 1024 // 1024} MB limit'
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)
    return True, ''


def _extract_flask_zip(zip_path: Path, dest: Path) -> None:
    """Extract ZIP to dest, skipping macOS metadata, stripping top-level folder if present."""
    root = dest.resolve()
    # Detect common root folder (e.g. myapp/app.py → strip myapp/)
    strip_prefix: str | None = None
    with zipfile.ZipFile(zip_path, 'r') as zf:
        parts_set: set[str] = set()
        for info in zf.infolist():
            n = (info.filename or '').replace('\\', '/').strip().rstrip('/')
            if not n:
                continue
            parts = [p for p in n.split('/') if p]
            if len(parts) >= 2:
                parts_set.add(parts[0])
        if len(parts_set) == 1:
            strip_prefix = parts_set.pop() + '/'

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            name = (info.filename or '').replace('\\', '/').strip()
            if not name:
                continue
            # Skip macOS metadata
            parts_raw = name.split('/')
            if parts_raw[0] == '__MACOSX' or any(p.startswith('._') for p in parts_raw):
                continue
            if strip_prefix and name.startswith(strip_prefix):
                name = name[len(strip_prefix):]
            if not name:
                continue
            parts = [p.lower() for p in name.rstrip('/').split('/') if p]
            lowered = '/'.join(parts)
            if not lowered:
                continue
            is_dir = name.endswith('/') or info.is_dir()
            rel = Path(lowered)
            if '..' in rel.parts or rel.is_absolute():
                raise ValueError(f'Unsafe path: {name!r}')
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f'Path escapes dest: {name!r}')
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, 'r') as src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)
            now = time.time()
            import os; os.utime(target, (now, now))


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
    ok, err = _validate_flask_zip(zip_path)
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
        _extract_flask_zip(zip_path, site_dir)
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
