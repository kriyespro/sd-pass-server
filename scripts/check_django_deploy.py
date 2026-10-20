#!/usr/bin/env python3
"""
Pre-deployment readiness check for a Django project headed to this platform
(sd-pass-server). Run it once your app is finished, from inside the project
folder, BEFORE you push to GitHub / upload a ZIP:

    python3 check_django_deploy.py .

Or against a folder path or a ready-made ZIP from anywhere:

    python3 check_django_deploy.py /path/to/your/django/project
    python3 check_django_deploy.py /path/to/your/project.zip

This is the one general command for every Django app on this platform — it
mirrors the platform's actual deploy rules exactly (same limits, same
file-type policy, same entry-point/requirements/DATABASE_URL detection as
flask_runner/runner.py and apps/deployments/django_deploy.py) and also
catches the real-world failure modes this platform has actually hit:
missing requirements/ splits, unread DATABASE_URL (silent sqlite3
fallback), django-axes misconfiguration, hardcoded DEBUG/SECRET_KEY, and
models with no migrations. A clean run here means the deploy won't fail
for any reason this platform has seen in practice.

If run from inside your project's own virtualenv (Django importable), it
also runs `manage.py check` and `manage.py makemigrations --check --dry-run`
against a dummy DATABASE_URL — the same way the platform itself validates
on deploy, minus an actual Postgres connection. Skipped automatically
otherwise (still a passable run: the script needs no dependencies itself).

Exit code 0 = no blocking issues. Exit code 1 = at least one blocking issue
(the deploy WILL fail). Warnings never set a non-zero exit code.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
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
# These four are always installed by the platform before your requirements
# file — unpinned, whatever is latest on PyPI at deploy time. If you don't
# pin them yourself, the version you deploy with can silently differ from
# whatever you tested locally.
_BASE_PACKAGES = ('django', 'gunicorn', 'psycopg2-binary', 'django-environ')

PASS = '\033[92m✅\033[0m'
WARN = '\033[93m⚠️ \033[0m'
FAIL = '\033[91m❌\033[0m'
INFO = 'ℹ️ '


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

    def dir_exists(self, rel_path):
        return (self.root / rel_path).is_dir()


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
        self._dirs: set[str] = set()
        for m in members:
            name = m.filename.replace('\\', '/')
            if self.strip_prefix and name.startswith(self.strip_prefix):
                name = name[len(self.strip_prefix):]
            if name:
                self._index[name] = m
                parts = name.split('/')[:-1]
                for i in range(1, len(parts) + 1):
                    self._dirs.add('/'.join(parts[:i]))

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

    def dir_exists(self, rel_path):
        return rel_path.rstrip('/') in self._dirs


# manage.py's hardcoded DJANGO_SETTINGS_MODULE default is very commonly a DEV
# settings module (config.settings.dev) — correct for local development, but
# this platform only ever runs in production. A dev settings module commonly
# hardcodes a local sqlite3 database (silently ignoring the Postgres
# DATABASE_URL this platform injects, so every redeploy wipes whatever was in
# that sqlite file since it isn't part of the git repo) and DEBUG=True. If a
# sibling prod/production module exists next to the detected one, the
# platform prefers it — exactly like requirements/prod.txt is preferred over
# requirements/dev.txt. Mirrors flask_runner/runner.py's own version of this.
_DEV_SETTINGS_NAMES = frozenset({'dev', 'development', 'local', 'debug'})
_PROD_SETTINGS_CANDIDATES = ('prod', 'production', 'release')


def _prefer_production_settings(src: Source, settings_module: str) -> tuple[str, list[str]]:
    problems = []
    parts = settings_module.split('.')
    if parts[-1].lower() not in _DEV_SETTINGS_NAMES:
        return settings_module, problems

    settings_dir = '/'.join(parts[:-1])
    for candidate in _PROD_SETTINGS_CANDIDATES:
        rel = f'{settings_dir}/{candidate}.py' if settings_dir else f'{candidate}.py'
        if src.exists(rel):
            resolved = '.'.join(parts[:-1] + [candidate])
            problems.append(
                WARN + f' manage.py defaults to dev-looking "{settings_module}" — the platform '
                f'will use "{resolved}" instead (found alongside it), since this is always a '
                'production deploy. Double-check that module is really meant for this.'
            )
            return resolved, problems

    problems.append(
        WARN + f' DJANGO_SETTINGS_MODULE is "{settings_module}", which looks like a dev '
        'settings module, and no sibling prod/production module was found next to it. Dev '
        'settings commonly hardcode a local sqlite3 database (silently ignoring the '
        'DATABASE_URL this platform injects) and DEBUG=True — if this one does too, every '
        "single redeploy silently wipes all data, since the sqlite file lives inside the "
        "extracted site folder and isn't part of your git repo. See the Database config "
        'section below — if it also warns about DATABASE_URL, treat this as serious.'
    )
    return settings_module, problems


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

    settings_module, pref_problems = _prefer_production_settings(src, match.group(1))
    problems.extend(pref_problems)
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


def check_version_pins(src: Source, req_file: str | None) -> list[str]:
    """The platform always installs django/gunicorn/psycopg2-binary/django-environ
    UNPINNED before your requirements file. If your own requirements don't pin
    them either, you deploy on whatever is latest on PyPI that day — which can
    silently differ from the version you actually developed and tested with."""
    if not req_file:
        return []
    text = src.read_text(req_file) or ''
    pinned = {
        re.match(r'^\s*([A-Za-z0-9_.\-]+)', line).group(1).lower()
        for line in text.splitlines()
        if re.match(r'^\s*[A-Za-z0-9_.\-]+\s*==', line)
    }
    unpinned = [pkg for pkg in _BASE_PACKAGES if pkg.lower() not in pinned]
    if not unpinned:
        return []
    return [
        WARN + f' {", ".join(unpinned)} not pinned (==) in {req_file} — the platform will '
        'install whatever is latest on PyPI at deploy time for these, which may differ from '
        'what you developed/tested against locally. Pin them explicitly if that matters '
        '(e.g. Django==5.2.17).'
    ]


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


def _settings_files_text(src: Source, settings_module: str) -> list[tuple[str, str]]:
    package = settings_module.split('.')[0]
    out = []
    for rel, _size in src.files():
        if rel.startswith(f'{package}/') and rel.endswith('.py'):
            text = src.read_text(rel)
            if text:
                out.append((rel, text))
    return out


def check_axes_config(src: Source, settings_module: str | None) -> list[str]:
    """django-axes (login-lockout) is easy to half-configure: the backend must
    come FIRST in AUTHENTICATION_BACKENDS, and a lockout only ever clears via
    axes.utils.reset() — this platform's superadmin reset already does that,
    but only if axes is actually wired up the way it expects."""
    if not settings_module:
        return []
    files = _settings_files_text(src, settings_module)
    all_text = '\n'.join(text for _rel, text in files)
    if "'axes'" not in all_text and '"axes"' not in all_text:
        return []  # project doesn't use django-axes at all — nothing to check

    problems = []
    backends_match = re.search(r'AUTHENTICATION_BACKENDS\s*=\s*\[([^\]]*)\]', all_text, re.DOTALL)
    if not backends_match:
        problems.append(
            WARN + " 'axes' is installed but AUTHENTICATION_BACKENDS isn't set — "
            "add 'axes.backends.AxesStandaloneBackend' first, then "
            "'django.contrib.auth.backends.ModelBackend'."
        )
    else:
        backends_block = backends_match.group(1)
        entries = [e.strip().strip("'\"") for e in backends_block.split(',') if e.strip()]
        axes_backends = [e for e in entries if 'axes' in e.lower()]
        if not axes_backends:
            problems.append(
                WARN + " 'axes' is installed but no axes backend is in AUTHENTICATION_BACKENDS — "
                'login lockout silently does nothing without it.'
            )
        elif entries and entries[0] not in axes_backends:
            problems.append(
                WARN + ' The axes backend must be FIRST in AUTHENTICATION_BACKENDS — '
                f'found {entries[0]!r} first instead. Per django-axes docs, put it first '
                'or lockouts can be bypassed by the backend ahead of it.'
            )
    if 'axes.middleware.AxesMiddleware' not in all_text:
        problems.append(
            WARN + " 'axes' is installed but 'axes.middleware.AxesMiddleware' isn't in "
            'MIDDLEWARE — required for axes to actually intercept logins.'
        )
    return problems


def check_hardcoded_secrets(src: Source, settings_module: str | None) -> list[str]:
    if not settings_module:
        return []
    problems = []
    for rel, text in _settings_files_text(src, settings_module):
        if re.search(r'^\s*DEBUG\s*=\s*True\b', text, re.MULTILINE):
            problems.append(
                WARN + f' {rel}: DEBUG = True is hardcoded. On this platform your app always '
                'runs with DEBUG on unless you read it from an env var — leaking stack traces '
                'and settings to visitors. Use DEBUG = env.bool("DEBUG", default=False).'
            )
        if re.search(r'''^\s*SECRET_KEY\s*=\s*['"][^'"]{10,}['"]''', text, re.MULTILINE):
            problems.append(
                WARN + f' {rel}: SECRET_KEY looks hardcoded as a literal string. Prefer '
                'SECRET_KEY = env("SECRET_KEY") so it isn\'t sitting in your Git history.'
            )
    return problems


def check_migrations_present(src: Source) -> list[str]:
    """A models.py with no migrations/ next to it means Django silently never
    creates that app's tables — no error at migrate time, just "no such
    table" the first time a view touches that model."""
    problems = []
    models_dirs = set()
    for rel, _size in src.files():
        if rel.endswith('/models.py') or rel == 'models.py':
            models_dirs.add(str(Path(rel).parent))
        if '/models/' in f'/{rel}' and rel.endswith('__init__.py'):
            models_dirs.add(str(Path(rel).parent.parent))

    for app_dir in sorted(models_dirs):
        migrations_dir = f'{app_dir}/migrations' if app_dir != '.' else 'migrations'
        has_migration_files = any(
            rel.startswith(f'{migrations_dir}/') and rel.endswith('.py')
            and not rel.endswith('__init__.py')
            for rel, _size in src.files()
        )
        if not has_migration_files:
            problems.append(
                WARN + f' {app_dir}/models.py has no migrations in {migrations_dir}/ — '
                'run `manage.py makemigrations` and commit the result, or this app\'s '
                'tables silently never get created.'
            )
    return problems


def run_deep_check(target: Path, settings_module: str | None) -> list[str]:
    """Best-effort: if this script is running inside an environment that
    already has Django installed, actually run `manage.py check` and
    `makemigrations --check --dry-run` the way the platform's own deploy
    does — against a dummy DATABASE_URL (never connected to, just parsed)
    so missing env vars don't block it. Silently skipped if Django isn't
    importable; that's expected when running from a bare system Python."""
    try:
        import django  # noqa: F401
    except ImportError:
        return [
            INFO + ' Skipped deep check (manage.py check / makemigrations --check) — Django '
            "isn't installed in this Python. Run this script from inside your project's own "
            'activated virtualenv for that extra coverage.'
        ]

    if not settings_module or not (target / 'manage.py').is_file():
        return []

    # A dummy sqlite DSN, outside the project dir (never connected to, never
    # queried — just needs to parse as a valid DATABASE_URL and resolve to an
    # always-importable backend, so settings.py doesn't raise
    # ImproperlyConfigured before `check` / `makemigrations` can even run).
    # sqlite3, not postgres: Django's check framework imports the DB backend
    # module even without connecting, and psycopg2 may not be installed in
    # your local dev venv at all — the real platform always has it, this
    # check just doesn't need it to run.
    dummy_db_path = Path(tempfile.gettempdir()) / 'check_django_deploy_dummy.sqlite3'
    env = dict(os.environ)
    env['DJANGO_SETTINGS_MODULE'] = settings_module
    env.setdefault('DATABASE_URL', f'sqlite:///{dummy_db_path.as_posix()}')
    env.setdefault('SECRET_KEY', 'check-django-deploy-dummy-key')
    env['PYTHONPATH'] = str(target)

    problems = []
    try:
        r = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            cwd=str(target), env=env, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            problems.append(FAIL + ' `manage.py check` failed:\n' + _indent(r.stderr or r.stdout))
        else:
            problems.append(PASS + ' `manage.py check` passed')
    except subprocess.TimeoutExpired:
        problems.append(WARN + ' `manage.py check` timed out after 60s')
    except OSError as exc:
        problems.append(WARN + f' Could not run `manage.py check`: {exc}')

    try:
        r = subprocess.run(
            [sys.executable, 'manage.py', 'makemigrations', '--check', '--dry-run'],
            cwd=str(target), env=env, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            problems.append(
                WARN + ' Your models have changes with no migration committed for them '
                '(`makemigrations --check` failed):\n' + _indent(r.stderr or r.stdout)
            )
        else:
            problems.append(PASS + ' No missing migrations (`makemigrations --check` passed)')
    except subprocess.TimeoutExpired:
        problems.append(WARN + ' `makemigrations --check` timed out after 60s')
    except OSError as exc:
        problems.append(WARN + f' Could not run `makemigrations --check`: {exc}')

    return problems


def _indent(text: str, prefix: str = '      ') -> str:
    lines = (text or '').strip().splitlines()
    return '\n'.join(prefix + line for line in lines[-15:])


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
    report(check_version_pins(src, req_file))

    print('\n── Database config ──────────────────────────────────────')
    problems = check_database_config(src, settings_module)
    if not problems:
        print(PASS + ' settings.py reads DATABASE_URL (or no DATABASES override to worry about)')
    report(problems)

    print('\n── django-axes (if used) ────────────────────────────────')
    problems = check_axes_config(src, settings_module)
    if not problems:
        print(PASS + ' No django-axes misconfiguration found')
    report(problems)

    print('\n── Settings hygiene ─────────────────────────────────────')
    problems = check_hardcoded_secrets(src, settings_module)
    if not problems:
        print(PASS + ' No hardcoded DEBUG=True / literal SECRET_KEY found')
    report(problems)

    print('\n── Migrations ───────────────────────────────────────────')
    problems = check_migrations_present(src)
    if not problems:
        print(PASS + ' Every models.py has a matching migrations/ directory')
    report(problems)

    print('\n── Contents (file count / size / type) ─────────────────')
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

    if isinstance(src, DirSource):
        print('\n── Deep check (manage.py, best-effort) ──────────────────')
        deep_problems = run_deep_check(target, settings_module)
        for p in deep_problems:
            print(p)
        blocking += sum(1 for p in deep_problems if p.startswith(FAIL))
        warnings += sum(1 for p in deep_problems if p.startswith(WARN))

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
