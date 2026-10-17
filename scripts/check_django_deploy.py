#!/usr/bin/env python3
"""
Pre-deployment check for a Django project headed to this platform.

Run it locally, against either a project folder or a ready-made ZIP, BEFORE
you push to GitHub / upload a ZIP. It mirrors the platform's actual deploy
rules exactly (same limits, same file-type policy, same entry-point
detection as flask_runner/runner.py and apps/deployments/django_deploy.py),
so a clean run here means the deploy won't fail for any of the reasons this
platform has hit in practice.

Usage:
    python3 check_django_deploy.py /path/to/your/django/project
    python3 check_django_deploy.py /path/to/your/project.zip

Zero dependencies — stdlib only, runs on a bare macOS/Linux Python 3.

Exit code 0 = no blocking issues. Exit code 1 = at least one blocking issue
(the deploy WILL fail). Warnings never set a non-zero exit code.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

# ── Mirrors apps/deployments/python_zip_utils.py ───────────────────────────
BLOCKED_SUFFIXES = frozenset({
    '.exe', '.dll', '.so', '.dylib', '.msi', '.com', '.scr', '.bin', '.app',
})
_NOISE_DIR_SEGMENTS = frozenset({
    '__pycache__', '__macosx', 'node_modules', '.git', '.tox',
    'venv', '.venv', 'env', 'site-packages', 'dist-packages',
})

# ── Mirrors apps/deployments/django_deploy.py ───────────────────────────────
MAX_DJANGO_ZIP_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_DJANGO_FILES = 500

# ── Mirrors flask_runner/runner.py ──────────────────────────────────────────
_DJANGO_SETTINGS_RE = re.compile(
    r"""setdefault\(\s*['"]DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]\s*\)"""
)
_REQUIREMENTS_CANDIDATES = (
    'requirements.txt',
    'requirements/production.txt',
    'requirements/prod.txt',
    'requirements/base.txt',
    'requirements/common.txt',
    'requirements/dev.txt',
    'requirements/local.txt',
    'requirements/development.txt',
)

PASS = '\033[92m✅\033[0m'
WARN = '\033[93m⚠️ \033[0m'
FAIL = '\033[91m❌\033[0m'


def _is_ignored(parts: list[str]) -> bool:
    lowered = [p.lower() for p in parts]
    return any(p in _NOISE_DIR_SEGMENTS for p in lowered) or any(p.startswith('._') for p in parts)


class Source:
    """Uniform view over either an extracted directory or a ZIP, read-only."""

    def files(self) -> list[tuple[str, int]]:
        """Return [(relative_posix_path, size_bytes), ...] excluding noise/ignored entries."""
        raise NotImplementedError

    def read_text(self, rel_path: str) -> str | None:
        raise NotImplementedError

    def exists(self, rel_path: str) -> bool:
        raise NotImplementedError


class DirSource(Source):
    def __init__(self, root: Path):
        self.root = root

    def files(self):
        out = []
        for p in self.root.rglob('*'):
            if p.is_dir():
                continue
            rel = p.relative_to(self.root)
            if _is_ignored(rel.parts):
                continue
            try:
                out.append((rel.as_posix(), p.stat().st_size))
            except OSError:
                pass
        return out

    def read_text(self, rel_path):
        p = self.root / rel_path
        try:
            return p.read_text(errors='ignore')
        except OSError:
            return None

    def exists(self, rel_path):
        return (self.root / rel_path).is_file()


class ZipSource(Source):
    def __init__(self, zip_path: Path):
        self.zf = zipfile.ZipFile(zip_path, 'r')
        members = [m for m in self.zf.infolist() if not m.is_dir()]
        # Mirror extract_zip()'s "strip the single common top folder" behavior.
        parts_set = set()
        for m in members:
            parts = [p for p in m.filename.replace('\\', '/').split('/') if p]
            if len(parts) >= 2:
                parts_set.add(parts[0])
        self.strip_prefix = parts_set.pop() + '/' if len(parts_set) == 1 else None
        self._index: dict[str, zipfile.ZipInfo] = {}
        for m in members:
            name = m.filename.replace('\\', '/')
            if self.strip_prefix and name.startswith(self.strip_prefix):
                name = name[len(self.strip_prefix):]
            if name:
                self._index[name] = m

    def files(self):
        out = []
        for name, m in self._index.items():
            parts = [p for p in name.split('/') if p]
            if _is_ignored(parts):
                continue
            out.append((name, m.file_size))
        return out

    def read_text(self, rel_path):
        m = self._index.get(rel_path)
        if not m:
            return None
        try:
            return self.zf.read(m).decode('utf-8', errors='ignore')
        except (KeyError, zipfile.BadZipFile):
            return None

    def exists(self, rel_path):
        return rel_path in self._index


def detect_django_entry(src: Source) -> tuple[str | None, str | None, list[str]]:
    """Returns (settings_module, wsgi_target, problems)."""
    problems = []
    if not src.exists('manage.py'):
        problems.append(
            FAIL + ' No manage.py at the project root. The platform looks for it exactly '
            'there (not one level deep) — this is the single most common reason a pull fails.'
        )
        return None, None, problems

    text = src.read_text('manage.py') or ''
    match = _DJANGO_SETTINGS_RE.search(text)
    if not match:
        problems.append(
            FAIL + " manage.py doesn't contain the standard "
            '`os.environ.setdefault("DJANGO_SETTINGS_MODULE", "...")` line — '
            'entry-point detection needs it verbatim.'
        )
        return None, None, problems

    settings_module = match.group(1)
    package = settings_module.split('.')[0]
    wsgi_rel = f'{package}/wsgi.py'
    if src.exists(wsgi_rel):
        return settings_module, f'{package}.wsgi:application', problems

    # Fallback: any wsgi.py anywhere (mirrors runner.py's fallback).
    for rel, _size in src.files():
        if rel.endswith('/wsgi.py') or rel == 'wsgi.py':
            module = rel[:-3].replace('/', '.')
            problems.append(
                WARN + f' No {wsgi_rel} — falling back to {rel}. This works but double-check '
                "it's really your project's WSGI module."
            )
            return settings_module, f'{module}:application', problems

    problems.append(
        FAIL + f' DJANGO_SETTINGS_MODULE is "{settings_module}" but no {wsgi_rel} '
        '(or any wsgi.py) was found.'
    )
    return settings_module, None, problems


def find_requirements(src: Source) -> tuple[str | None, list[str]]:
    problems = []
    for candidate in _REQUIREMENTS_CANDIDATES:
        if src.exists(candidate):
            if candidate != 'requirements.txt':
                problems.append(
                    WARN + f' Using {candidate} (no plain requirements.txt at the root). '
                    'This works, but confirm it actually pulls in everything your app needs.'
                )
            return candidate, problems
    problems.append(
        FAIL + ' No requirements.txt (or requirements/{prod,base,dev}.txt) found. '
        'Only django, gunicorn, psycopg2-binary, and django-environ get installed — '
        'anything else your app imports will fail at runtime.'
    )
    return None, problems


def check_database_config(src: Source, settings_module: str | None) -> list[str]:
    problems = []
    if not settings_module:
        return problems
    package = settings_module.split('.')[0]
    # Search every .py file under the settings package for how DATABASES is built.
    found_env_db = False
    found_databases = False
    for rel, _size in src.files():
        if not rel.startswith(f'{package}/') or not rel.endswith('.py'):
            continue
        text = src.read_text(rel) or ''
        if 'DATABASES' in text:
            found_databases = True
        if re.search(r'env\.db\s*\(|dj_database_url|DATABASE_URL', text):
            found_env_db = True
    if found_databases and not found_env_db:
        problems.append(
            WARN + ' settings.py sets DATABASES but nothing references DATABASE_URL / env.db(...) — '
            'the platform injects a Postgres DATABASE_URL at deploy time; if your settings.py '
            "doesn't read it, migrate will run against whatever DATABASES already says "
            '(often sqlite3, which silently loses data between deploys). '
            "Use: DATABASES = {'default': env.db('DATABASE_URL')} (django-environ is "
            'pre-installed, no need to add it to requirements.txt).'
        )
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1

    target = Path(sys.argv[1]).expanduser().resolve()
    if not target.exists():
        print(FAIL + f' Path does not exist: {target}')
        return 1

    if target.is_dir():
        src: Source = DirSource(target)
        print(f'Checking directory: {target}\n')
    elif target.suffix.lower() == '.zip':
        src = ZipSource(target)
        print(f'Checking ZIP: {target}\n')
    else:
        print(FAIL + ' Pass a project directory or a .zip file.')
        return 1

    blocking = 0
    warnings = 0

    def report(problems: list[str]):
        nonlocal blocking, warnings
        for p in problems:
            print(p)
            if p.startswith(FAIL):
                blocking += 1
            elif p.startswith(WARN):
                warnings += 1

    print('── Entry point ──────────────────────────────────────────')
    settings_module, wsgi_target, problems = detect_django_entry(src)
    if not problems:
        print(PASS + f' manage.py found, settings module: {settings_module}, WSGI: {wsgi_target}')
    report(problems)

    print('\n── Dependencies ─────────────────────────────────────────')
    req_file, problems = find_requirements(src)
    if req_file and not problems:
        print(PASS + f' Found {req_file}')
    report(problems)

    print('\n── Database config ──────────────────────────────────────')
    problems = check_database_config(src, settings_module)
    if not problems:
        print(PASS + ' settings.py reads DATABASE_URL (or no DATABASES override to worry about)')
    report(problems)

    print('\n── ZIP contents (file count / size / type) ─────────────')
    files = src.files()
    total_size = sum(size for _name, size in files)
    blocked_hits = [name for name, _size in files if Path(name).suffix.lower() in BLOCKED_SUFFIXES]

    if len(files) > MAX_DJANGO_FILES:
        report([FAIL + f' {len(files)} files (max {MAX_DJANGO_FILES}). Check for a committed '
                        'venv/, node_modules/, or other large folder that should be .gitignore\'d.'])
    else:
        print(PASS + f' {len(files)} files (limit {MAX_DJANGO_FILES})')

    if total_size > MAX_DJANGO_ZIP_SIZE:
        report([FAIL + f' Contents total {total_size // 1024 // 1024} MB '
                        f'(max {MAX_DJANGO_ZIP_SIZE // 1024 // 1024} MB).'])
    else:
        print(PASS + f' {total_size // 1024} KB total (limit {MAX_DJANGO_ZIP_SIZE // 1024 // 1024} MB)')

    if blocked_hits:
        report([FAIL + f' Blocked file type(s): {", ".join(blocked_hits[:10])}'
                        + (f' (+{len(blocked_hits) - 10} more)' if len(blocked_hits) > 10 else '')
                        + ' — executables/native binaries are never allowed.'])
    else:
        print(PASS + ' No blocked (executable/binary) file types')

    print('\n────────────────────────────────────────────────────────')
    if blocking:
        print(FAIL + f' {blocking} blocking issue(s) — this deploy WILL fail. Fix them and re-run.')
        return 1
    if warnings:
        print(WARN + f' {warnings} warning(s) — likely to deploy, but double-check them.')
        return 0
    print(PASS + ' All checks passed — should deploy cleanly.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
