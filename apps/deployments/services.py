"""Student static sites: ZIP extract (Celery) and multi-file save (web)."""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

from django.conf import settings

from apps.projects.models import Project, ProjectType

MAX_STATIC_FILES_PER_POST = 200

MAX_STATIC_PATH_SEGMENTS = 32
MAX_STATIC_REL_PATH_CHARS = 512

STATIC_ASSET_SUFFIXES = frozenset(
    {
        '.html',
        '.htm',
        '.css',
        '.js',
        '.mjs',
        '.json',
        '.svg',
        '.map',
        '.woff',
        '.woff2',
        '.ttf',
        '.eot',
        '.otf',
        '.ico',
        '.png',
        '.jpg',
        '.jpeg',
        '.gif',
        '.webp',
        '.webmanifest',
    }
)


def project_site_dir(project: Project) -> Path:
    root = Path(settings.STUDENT_SITE_ROOT)
    return root / str(project.pk)


def extract_static_site_from_zip(project: Project, zip_path: Path) -> tuple[bool, str]:
    """
    Unpack a ZIP into STUDENT_SITE_ROOT/<project_id>/ for static (HTML) projects.
    Returns (ok, message). On failure the previous bundle is removed if present.
    """
    if project.project_type != ProjectType.STATIC:
        return False, 'skip_non_static_project'

    dest = project_site_dir(project)
    try:
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        _safe_unzip(zip_path, dest)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return False, str(exc)

    index = dest / 'index.html'
    if not index.is_file():
        return True, 'extracted_no_index_html'

    return True, 'extracted_ok'


def _safe_unzip(zip_path: Path, dest: Path) -> None:
    root = dest.resolve()
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            name = (info.filename or '').replace('\\', '/').strip()
            if not name or name.startswith('/') or '..' in name.split('/'):
                raise ValueError(f'Unsafe ZIP entry: {name!r}')
            rel = Path(name)
            if '..' in rel.parts:
                raise ValueError(f'Unsafe ZIP path: {name!r}')
            if rel.is_absolute():
                raise ValueError(f'Absolute ZIP path: {name!r}')
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f'Path escapes site root: {name!r}')
            if name.endswith('/'):
                target.mkdir(parents=True, exist_ok=True)
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, 'r') as src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)


def _safe_rel_path_for_static_upload(raw_name: str, dest: Path) -> tuple[bool, str, Path]:
    """
    Treat uploaded.name as a relative path (flat name or images/foo.png from folder picker).
    Returns (ok, error_code_or_detail, Path relative to dest).
    """
    name = (raw_name or '').replace('\\', '/').strip()
    if not name or name.startswith('/'):
        return False, f'invalid_filename:{raw_name!r}', Path()
    parts = [p for p in name.split('/') if p and p != '.']
    if not parts or '..' in parts:
        return False, f'invalid_filename:{raw_name!r}', Path()
    if len(parts) > MAX_STATIC_PATH_SEGMENTS:
        return False, 'path_too_deep', Path()
    if len(name) > MAX_STATIC_REL_PATH_CHARS:
        return False, 'path_too_long', Path()
    rel_path = Path(*parts)
    try:
        root = dest.resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root):
            return False, f'invalid_filename:{raw_name!r}', Path()
    except (ValueError, OSError):
        return False, f'invalid_filename:{raw_name!r}', Path()
    return True, '', rel_path


def save_static_files(project: Project, file_list: list) -> tuple[bool, str]:
    """
    Save multiple uploaded files under the static site directory (merge/overwrite).
    Accepts flat names (index.html) or relative paths (images/logo.png) from a folder upload.
    Only for Static projects. Total size must be within STUDENT_UPLOAD_MAX_BYTES.
    """
    if project.project_type != ProjectType.STATIC:
        return False, 'only_static_projects'

    if not file_list:
        return False, 'no_files'

    if len(file_list) > MAX_STATIC_FILES_PER_POST:
        return False, f'max_{MAX_STATIC_FILES_PER_POST}_files_per_request'

    max_bytes = settings.STUDENT_UPLOAD_MAX_BYTES
    dest = project_site_dir(project)
    dest.mkdir(parents=True, exist_ok=True)

    staged: list[tuple[Path, object]] = []
    total = 0
    seen_rel: set[str] = set()
    for uploaded in file_list:
        raw_name = uploaded.name or ''
        ok_path, err, rel_path = _safe_rel_path_for_static_upload(raw_name, dest)
        if not ok_path:
            return False, err
        rel_key = rel_path.as_posix()
        if rel_key in seen_rel:
            return False, f'duplicate_path:{rel_key}'
        seen_rel.add(rel_key)
        leaf = rel_path.name
        suf = Path(leaf).suffix.lower()
        if suf == '.zip':
            return False, 'use_zip_upload_for_archives'
        if suf not in STATIC_ASSET_SUFFIXES:
            return False, f'disallowed_type:{rel_key}'
        total += getattr(uploaded, 'size', 0) or 0
        if total > max_bytes:
            return False, 'total_size_exceeds_limit'
        staged.append((rel_path, uploaded))

    try:
        for rel_path, uploaded in staged:
            path = dest / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('wb') as out:
                for chunk in uploaded.chunks():
                    out.write(chunk)
    except OSError as exc:
        return False, str(exc)

    return True, f'saved_{len(staged)}_files'


def runtime_env_dir() -> Path:
    """Server-only directory for per-project env snapshots (not web-served)."""
    d = Path(settings.STUDENT_SITE_ROOT).parent / 'runtime_env'
    d.mkdir(parents=True, exist_ok=True)
    return d


def runtime_env_json_path(project: Project) -> Path:
    return runtime_env_dir() / f'{project.pk}.json'


def write_runtime_env_snapshot(project: Project, env_plain: dict[str, str]) -> None:
    """Write decrypted env as JSON for workers/runtime; remove file if empty."""
    path = runtime_env_json_path(project)
    if not env_plain:
        path.unlink(missing_ok=True)
        return
    path.write_text(
        json.dumps(env_plain, ensure_ascii=False, sort_keys=True),
        encoding='utf-8',
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def delete_runtime_env_snapshot(project: Project) -> None:
    runtime_env_json_path(project).unlink(missing_ok=True)


def project_site_has_files(project: Project) -> bool:
    root = project_site_dir(project)
    if not root.is_dir():
        return False
    return any(p.is_file() for p in root.iterdir())


def build_project_site_zip(project: Project) -> io.BytesIO | None:
    """Zip published site files under STUDENT_SITE_ROOT/<project_id>/."""
    root = project_site_dir(project)
    if not root.is_dir():
        return None
    files = [p for p in root.rglob('*') if p.is_file()]
    if not files:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = path.relative_to(root).as_posix()
            zf.write(path, arcname)
    buf.seek(0)
    return buf
