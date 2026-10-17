"""
Shared ZIP validate/extract helpers for Python app deployments (Flask, Django).
Framework-specific allow-lists and limits live in flask_deploy.py / django_deploy.py;
this module only knows about generic ZIP safety.
"""
from __future__ import annotations

import os
import shutil
import time
import zipfile
from pathlib import Path


def is_ignored_entry(name: str) -> bool:
    """Return True for __pycache__, .pyc/.pyo, macOS metadata — safe to skip silently."""
    parts = name.replace('\\', '/').split('/')
    return (
        '__pycache__' in parts
        or parts[0] == '__MACOSX'
        or any(p.startswith('._') for p in parts)
        or Path(name).suffix.lower() in ('.pyc', '.pyo')
    )


def validate_zip(
    zip_path: Path,
    *,
    allowed_suffixes: frozenset[str],
    allowed_filenames: frozenset[str],
    max_files: int,
    max_size: int,
) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]
            real_entries = [i for i in entries if not is_ignored_entry(
                (i.filename or '').replace('\\', '/').strip()
            )]
            if len(real_entries) > max_files:
                return False, f'ZIP contains {len(real_entries)} files (max {max_files})'
            total = 0
            for info in real_entries:
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or name.startswith('/') or '..' in name.split('/'):
                    return False, f'Unsafe ZIP entry: {name!r}'
                suf = Path(name).suffix.lower()
                basename = Path(name).name.lower()
                if basename not in allowed_filenames and suf and suf not in allowed_suffixes:
                    return False, (
                        f'File type not allowed: {name!r}. '
                        f'Allowed: Python, HTML, CSS, JS, SQLite, images, config files.'
                    )
                total += info.file_size
                if total > max_size:
                    return False, f'ZIP contents exceed {max_size // 1024 // 1024} MB limit'
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)
    return True, ''


def extract_zip(zip_path: Path, dest: Path) -> None:
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
            if is_ignored_entry(name):
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
            os.utime(target, (now, now))
