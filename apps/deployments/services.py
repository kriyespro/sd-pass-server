"""Student static sites: ZIP extract (Celery) and multi-file save (web)."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import time
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

IMAGE_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'})
MAX_IMAGE_BYTES: int | None = 300 * 1024

_SUBFOLDER_RE = re.compile(r'^[a-zA-Z0-9_\-][a-zA-Z0-9_\-/]*$')


def _validate_subfolder(s: str) -> tuple[bool, str]:
    if not s:
        return True, ''
    if len(s) > 64 or '..' in s or s.startswith('/') or s.endswith('/'):
        return False, 'invalid_subfolder'
    if not _SUBFOLDER_RE.match(s):
        return False, 'invalid_subfolder'
    return True, ''


def project_site_dir(project: Project) -> Path:
    root = Path(settings.STUDENT_SITE_ROOT)
    return root / str(project.pk)


def _detect_zip_strip_prefix(zip_path: Path) -> str | None:
    """
    Return the common root folder name to strip during extraction, or None.

    Mirrors _find_common_root_prefix logic: strip the top-level folder only when
    ALL files share the same first path segment AND that folder contains an index.html
    directly (e.g. test-html-website/index.html → strip 'test-html-website').

    This prevents ZIPs created by "compress folder" on macOS/Windows from landing
    one directory too deep (dest/test-html-website/index.html instead of dest/index.html).
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            first_parts: set[str] = set()
            names: list[str] = []
            for info in zf.infolist():
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or info.is_dir() or name.endswith('/'):
                    continue
                parts = [p for p in name.split('/') if p]
                if len(parts) < 2:
                    return None  # file at ZIP root → nothing to strip
                first_parts.add(parts[0])
                if len(first_parts) > 1:
                    return None  # multiple top-level entries
                names.append(name.lower())
            if not first_parts or not names:
                return None
            common = first_parts.pop()
            has_index = any(
                n in (common.lower() + '/index.html', common.lower() + '/index.htm')
                for n in names
            )
            return common if has_index else None
    except (OSError, zipfile.BadZipFile):
        return None


def _validate_zip_for_extraction(zip_path: Path) -> tuple[bool, str]:
    """
    Scan ZIP central directory for path-traversal and image-size violations.
    No disk writes — safe to call before wiping the existing site.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or name.startswith('/') or '..' in name.split('/'):
                    return False, f'Unsafe ZIP entry: {name!r}'
                rel = Path(name)
                if '..' in rel.parts or rel.is_absolute():
                    return False, f'Unsafe ZIP path: {name!r}'
                if name.endswith('/') or info.is_dir():
                    continue
                suf = Path(name).suffix.lower()
                if MAX_IMAGE_BYTES is not None and suf in IMAGE_SUFFIXES and info.file_size > MAX_IMAGE_BYTES:
                    return False, (
                        f'Image too large: {name!r} is {info.file_size // 1024} KB '
                        f'(max {MAX_IMAGE_BYTES // 1024} KB). Compress it before uploading.'
                    )
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)
    return True, ''


def extract_static_site_from_zip(project: Project, zip_path: Path, subfolder: str = '') -> tuple[bool, str]:
    """
    Unpack a ZIP into STUDENT_SITE_ROOT/<project_id>/[subfolder]/ for static (HTML) projects.
    If subfolder given, only that subfolder is wiped/replaced (rest of site preserved).
    Returns (ok, message). On failure the extraction target is removed if present.
    """
    if project.project_type != ProjectType.STATIC:
        return False, 'skip_non_static_project'

    # Validate the ZIP before touching the existing site so a bad upload
    # never leaves students with an empty site.
    ok, err = _validate_zip_for_extraction(zip_path)
    if not ok:
        return False, err

    site_root = project_site_dir(project)
    extract_dest = site_root / subfolder if subfolder else site_root
    try:
        if subfolder:
            if extract_dest.exists():
                shutil.rmtree(extract_dest)
            extract_dest.mkdir(parents=True, exist_ok=True)
        else:
            if site_root.exists():
                shutil.rmtree(site_root)
            site_root.mkdir(parents=True, exist_ok=True)
        _safe_unzip(zip_path, extract_dest)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if extract_dest.exists():
            shutil.rmtree(extract_dest, ignore_errors=True)
        return False, str(exc)

    index = extract_dest / 'index.html'
    if not index.is_file():
        return True, 'extracted_no_index_html'

    return True, 'extracted_ok'


def _safe_unzip(zip_path: Path, dest: Path) -> None:
    root = dest.resolve()
    strip_prefix = _detect_zip_strip_prefix(zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            name = (info.filename or '').replace('\\', '/').strip()
            if not name or name.startswith('/') or '..' in name.split('/'):
                raise ValueError(f'Unsafe ZIP entry: {name!r}')
            # Skip macOS metadata entries (__MACOSX/ folder and ._* files).
            parts_raw = name.split('/')
            if parts_raw[0] == '__MACOSX' or any(p.startswith('._') for p in parts_raw):
                continue
            # Strip the top-level folder prefix when the ZIP was created by compressing
            # a folder (e.g. test-html-website/index.html → index.html).
            if strip_prefix:
                prefix = strip_prefix + '/'
                if name.startswith(prefix):
                    name = name[len(prefix):]
                elif name.lower().startswith(prefix.lower()):
                    name = name[len(prefix):]
                if not name:
                    continue
            # Lowercase all path parts so ZIPs created on macOS/Windows work on Linux.
            parts = [p.lower() for p in name.rstrip('/').split('/') if p]
            lowered = '/'.join(parts)
            is_dir_entry = name.endswith('/') or info.is_dir()
            rel = Path(lowered) if lowered else Path(name)
            if '..' in rel.parts:
                raise ValueError(f'Unsafe ZIP path: {name!r}')
            if rel.is_absolute():
                raise ValueError(f'Absolute ZIP path: {name!r}')
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f'Path escapes site root: {name!r}')
            if is_dir_entry:
                target.mkdir(parents=True, exist_ok=True)
                continue
            suf = rel.suffix.lower()
            if MAX_IMAGE_BYTES is not None and suf in IMAGE_SUFFIXES and info.file_size > MAX_IMAGE_BYTES:
                raise ValueError(
                    f'Image too large: {name!r} is {info.file_size // 1024} KB '
                    f'(max {MAX_IMAGE_BYTES // 1024} KB). Compress it before uploading.'
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, 'r') as src, open(target, 'wb') as out:
                shutil.copyfileobj(src, out)
            # Force current mtime so browser cache sees file as changed after re-upload.
            now = time.time()
            os.utime(target, (now, now))


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
    # Lowercase all path segments so uploads from case-insensitive filesystems
    # (macOS/Windows) work on the Linux server without 404s from case mismatches.
    parts = [p.lower() for p in parts]
    rel_path = Path(*parts)
    try:
        root = dest.resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root):
            return False, f'invalid_filename:{raw_name!r}', Path()
    except (ValueError, OSError):
        return False, f'invalid_filename:{raw_name!r}', Path()
    return True, '', rel_path


def _find_common_root_prefix(raw_names: list[str]) -> str | None:
    """
    webkitdirectory folder-picker includes the selected folder name as the first
    path segment on every file: e.g. selecting "mysite/" sends "mysite/index.html"
    and "mysite/images/photo.jpg". Strip that prefix ONLY when the upload looks
    like a full site — i.e. ALL paths share the same first segment AND there is an
    index.html directly under that root ("mysite/index.html").

    This avoids stripping the prefix when students upload just a subfolder (e.g.
    selecting "images/" sends "images/photo.jpg" — those should land in images/).
    Returns None when no stripping should happen.
    """
    first_parts: set[str] = set()
    for name in raw_names:
        name = (name or '').replace('\\', '/').strip()
        parts = [p for p in name.split('/') if p and p != '.']
        if len(parts) < 2:
            return None
        first_parts.add(parts[0])
        if len(first_parts) > 1:
            return None

    if not first_parts:
        return None

    common_root = first_parts.pop()
    root_index = common_root + '/index.html'
    root_index_htm = common_root + '/index.htm'
    has_root_index = any(
        (n.replace('\\', '/').strip().lower() in (root_index, root_index_htm))
        for n in raw_names
    )
    return common_root if has_root_index else None


def save_static_files(project: Project, file_list: list, subfolder: str = '') -> tuple[bool, str]:
    """
    Save multiple uploaded files under the static site directory (merge/overwrite).
    Accepts flat names (index.html) or relative paths (images/logo.png) from a folder upload.
    Only for Static projects. Total size must be within STUDENT_UPLOAD_MAX_BYTES.
    If subfolder given, files land under <site_root>/<subfolder>/.
    """
    if project.project_type != ProjectType.STATIC:
        return False, 'only_static_projects'

    if not file_list:
        return False, 'no_files'

    if len(file_list) > MAX_STATIC_FILES_PER_POST:
        return False, f'max_{MAX_STATIC_FILES_PER_POST}_files_per_request'

    sub_ok, sub_err = _validate_subfolder(subfolder)
    if not sub_ok:
        return False, sub_err

    max_bytes = settings.STUDENT_UPLOAD_MAX_BYTES
    dest = project_site_dir(project)
    dest.mkdir(parents=True, exist_ok=True)

    # Strip the root folder name that webkitdirectory prepends to every filename
    # (e.g. "mysite/index.html" → "index.html", "mysite/images/photo.jpg" → "images/photo.jpg").
    common_root = _find_common_root_prefix([f.name or '' for f in file_list])

    staged: list[tuple[Path, object]] = []
    total = 0
    seen_rel: set[str] = set()
    for uploaded in file_list:
        raw_name = uploaded.name or ''
        if common_root:
            stripped = raw_name.replace('\\', '/').strip()
            prefix = common_root + '/'
            if stripped.startswith(prefix):
                raw_name = stripped[len(prefix):]
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
        if MAX_IMAGE_BYTES is not None and suf in IMAGE_SUFFIXES:
            file_size = getattr(uploaded, 'size', 0) or 0
            if file_size > MAX_IMAGE_BYTES:
                return False, f'image_too_large:{rel_key}'
        if subfolder:
            rel_path = Path(subfolder) / rel_path
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
            now = time.time()
            os.utime(path, (now, now))
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
