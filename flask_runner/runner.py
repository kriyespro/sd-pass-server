"""
App Runner — process manager for student Flask and Django apps.
Exposes a JSON HTTP API on port 6000 (internal Docker network only).
Django/Celery calls this API to deploy, stop, and check app status.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import venv
from pathlib import Path

from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [runner] %(message)s',
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

management_app = Flask(__name__)

SITES_ROOT = Path(os.environ.get('STUDENT_SITE_ROOT', '/app/data/sites'))
API_TOKEN = os.environ.get('FLASK_RUNNER_TOKEN', '')
GUNICORN_TIMEOUT = int(os.environ.get('GUNICORN_TIMEOUT', '30'))
PIP_TIMEOUT = int(os.environ.get('PIP_TIMEOUT', '180'))
DJANGO_MANAGE_TIMEOUT = int(os.environ.get('DJANGO_MANAGE_TIMEOUT', '120'))

# State file must live INSIDE SITES_ROOT — that's the only path actually backed by a
# persisted volume (docker-compose mounts sites_data:/app/data/sites, not /app/data).
# A sibling of SITES_ROOT is on the container's throwaway layer and is lost on rebuild/recreate.
_STATE_FILE = SITES_ROOT / '_runner_state.json'

# project_id (int) → subprocess.Popen
_procs: dict[int, subprocess.Popen] = {}
_lock = threading.Lock()


# ── auth ──────────────────────────────────────────────────────────────────────

@management_app.before_request
def _auth():
    if request.path == '/health':
        return None
    if API_TOKEN and request.headers.get('X-Runner-Token') != API_TOKEN:
        return jsonify({'error': 'unauthorized'}), 401


# ── state persistence ─────────────────────────────────────────────────────────

def _remove_from_state(project_id: int) -> None:
    """Remove project_id from the persisted state file."""
    try:
        existing: dict[str, int] = json.loads(_STATE_FILE.read_text()) if _STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    existing.pop(str(project_id), None)
    try:
        SITES_ROOT.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(existing, indent=2))
    except OSError as exc:
        log.warning('Could not update runner state: %s', exc)


def _save_state_with_port(
    project_id: int, port: int, project_type: str = 'flask', env: dict[str, str] | None = None,
) -> None:
    """Persist project_id→{port,type,env} mapping then write live state."""
    existing: dict[str, dict] = {}
    try:
        existing = json.loads(_STATE_FILE.read_text()) if _STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        pass
    existing[str(project_id)] = {'port': port, 'type': project_type, 'env': env or {}}
    try:
        SITES_ROOT.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(existing, indent=2))
        _STATE_FILE.chmod(0o600)
    except OSError as exc:
        log.warning('Could not save runner state: %s', exc)


def _restore_state() -> None:
    """On startup, re-launch gunicorn for every project saved in state file."""
    if not _STATE_FILE.exists():
        return
    try:
        saved: dict[str, object] = json.loads(_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning('Could not read runner state file: %s', exc)
        return

    if not saved:
        return

    log.info('Restoring %d app(s) from state file', len(saved))
    for pid_str, value in saved.items():
        try:
            project_id = int(pid_str)
        except ValueError:
            continue
        # Backward compat: old state files stored a bare port int (always Flask, no env).
        if isinstance(value, dict):
            port = value.get('port')
            project_type = value.get('type', 'flask')
            saved_env = value.get('env') or {}
        else:
            port = value
            project_type = 'flask'
            saved_env = {}
        if not port:
            continue

        project_dir = _project_dir(project_id)
        if not project_dir.exists():
            log.warning('Restore: project dir missing for %s — skipping', project_id)
            continue

        extra_env: dict[str, str] = dict(saved_env)
        if project_type == 'django':
            django_info = _detect_django_entry(project_dir)
            if not django_info:
                log.warning('Restore: no Django entry point for project %s — skipping', project_id)
                continue
            settings_module, entry = django_info
            extra_env['DJANGO_SETTINGS_MODULE'] = settings_module
        else:
            entry = _detect_entry(project_dir)
            if not entry:
                log.warning('Restore: no entry point for project %s — skipping', project_id)
                continue

        ok, err = _setup_venv(project_id, project_type)
        if not ok:
            log.error('Restore: venv setup failed for project %s: %s', project_id, err)
            continue

        if project_type == 'django':
            ok, err = _run_django_management(project_id, extra_env)
            if not ok:
                log.error('Restore: manage.py step failed for project %s: %s', project_id, err)
                continue
            entry = _write_platform_wsgi_wrapper(project_dir, extra_env['DJANGO_SETTINGS_MODULE'], entry)

        gunicorn = _venv_bin(project_id, 'gunicorn')
        env = _student_env(project_dir, extra_env)
        try:
            proc = subprocess.Popen(
                [
                    str(gunicorn),
                    '-b', f'0.0.0.0:{port}',
                    '--workers', '1',
                    '--threads', '2',
                    '--timeout', str(GUNICORN_TIMEOUT),
                    '--access-logfile', '-',
                    '--error-logfile', '-',
                    entry,
                ],
                cwd=str(project_dir),
                env=env,
            )
        except OSError as exc:
            log.error('Restore: failed to start project %s: %s', project_id, exc)
            continue

        with _lock:
            _procs[project_id] = proc
        log.info('Restored project %s  type=%s  entry=%s  port=%s  pid=%s', project_id, project_type, entry, port, proc.pid)


# ── helpers ───────────────────────────────────────────────────────────────────

def _tail(text: str, n: int = 4000) -> str:
    """Last n chars of text — Python tracebacks put the actual exception type and
    message at the END, so a head-slice (the old [:600] behavior) routinely cut
    errors off before reaching anything useful. Error messages here flow into an
    unbounded LogEntry.message TextField, so there's no reason to be stingy."""
    text = text or ''
    return text[-n:]


# Safe environment for student gunicorn processes — no platform secrets inherited.
_STUDENT_ENV_ALLOWLIST = frozenset({
    'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'LC_CTYPE',
    'TMPDIR', 'TEMP', 'TMP', 'TERM',
})


def _student_env(project_dir: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal env for student gunicorn — strips platform secrets."""
    base = {k: v for k, v in os.environ.items() if k in _STUDENT_ENV_ALLOWLIST}
    base['PYTHONPATH'] = str(project_dir)
    if extra:
        base.update(extra)
    return base


def _project_dir(project_id: int) -> Path:
    return SITES_ROOT / str(project_id)


def _venv_bin(project_id: int, binary: str) -> Path:
    return _project_dir(project_id) / '.venv' / 'bin' / binary


def _detect_entry(project_dir: Path) -> str | None:
    """
    Return a gunicorn app spec like 'app:app'.
    Checks common entry-point filenames and scans for Flask() instantiation.
    """
    for fname in ('app.py', 'main.py', 'wsgi.py', 'run.py', 'application.py'):
        fpath = project_dir / fname
        if not fpath.exists():
            continue
        module = fname[:-3]
        try:
            text = fpath.read_text(errors='ignore')
        except OSError:
            continue
        for var in ('app', 'application', 'server'):
            if f'{var} = Flask(' in text or f'{var}=Flask(' in text:
                return f'{module}:{var}'
        return f'{module}:app'
    return None


_DJANGO_SETTINGS_RE = re.compile(
    r"""setdefault\(\s*['"]DJANGO_SETTINGS_MODULE['"]\s*,\s*['"]([\w.]+)['"]\s*\)"""
)

# manage.py's hardcoded DJANGO_SETTINGS_MODULE default is very commonly a DEV
# settings module (config.settings.dev) -- correct for local development, but
# this platform only ever runs in production. A dev settings module commonly
# hardcodes a local sqlite3 database (silently ignoring the Postgres
# DATABASE_URL this platform injects, so every redeploy wipes whatever was in
# that sqlite file since it isn't part of the git repo) and DEBUG=True. If a
# sibling prod/production module exists next to the detected one, prefer it --
# exactly like requirements/prod.txt is preferred over requirements/dev.txt
# elsewhere in this pipeline.
_DEV_SETTINGS_NAMES = frozenset({'dev', 'development', 'local', 'debug'})
_PROD_SETTINGS_CANDIDATES = ('prod', 'production', 'release')


def _prefer_production_settings(project_dir: Path, settings_module: str) -> str:
    parts = settings_module.split('.')
    if parts[-1].lower() not in _DEV_SETTINGS_NAMES:
        return settings_module

    settings_dir = project_dir.joinpath(*parts[:-1])
    for candidate in _PROD_SETTINGS_CANDIDATES:
        if (settings_dir / f'{candidate}.py').is_file():
            resolved = '.'.join(parts[:-1] + [candidate])
            log.info(
                'Project %s: manage.py defaults to dev-looking %r — using %r instead.',
                project_dir.name, settings_module, resolved,
            )
            return resolved
    log.warning(
        "Project %s: manage.py's DJANGO_SETTINGS_MODULE (%r) looks like a dev settings "
        'module and no sibling prod/production module was found — using it as-is.',
        project_dir.name, settings_module,
    )
    return settings_module


def _detect_django_entry(project_dir: Path) -> tuple[str, str] | None:
    """
    Return (settings_module, wsgi_app_spec) for a Django project, or None if this
    doesn't look like one. settings_module e.g. 'myproject.settings'.
    wsgi_app_spec e.g. 'myproject.wsgi:application' (a gunicorn app target).
    """
    manage_py = project_dir / 'manage.py'
    if not manage_py.exists():
        return None
    try:
        text = manage_py.read_text(errors='ignore')
    except OSError:
        return None
    match = _DJANGO_SETTINGS_RE.search(text)
    if not match:
        return None
    settings_module = _prefer_production_settings(project_dir, match.group(1))
    package = settings_module.split('.')[0]

    wsgi_path = project_dir / package / 'wsgi.py'
    if wsgi_path.exists():
        return settings_module, f'{package}.wsgi:application'

    # Fallback: search for any wsgi.py under the project root.
    for candidate in project_dir.rglob('wsgi.py'):
        if '.venv' in candidate.parts or '__pycache__' in candidate.parts:
            continue
        rel = candidate.relative_to(project_dir).with_suffix('')
        module = '.'.join(rel.parts)
        return settings_module, f'{module}:application'

    return None


_PLATFORM_WSGI_WRAPPER_NAME = '_platform_wsgi_entry'


def _write_platform_wsgi_wrapper(project_dir: Path, settings_module: str, wsgi_target: str) -> str:
    """
    Write a tiny gunicorn entrypoint that patches two settings before importing
    the student's real WSGI app, and return its app spec:

    1. ALLOWED_HOSTS += "*" — `django-admin startproject` defaults this to [],
       which rejects every request with DisallowedHost. Each project here runs
       in its own isolated gunicorn process that Traefik only ever routes that
       project's own domain(s) to, so this check is redundant in this
       architecture.
    2. SECURE_PROXY_SSL_HEADER — Traefik terminates TLS and forwards to
       gunicorn over plain HTTP, so without this Django thinks every request
       is HTTP. That breaks the CSRF Origin check specifically: Django compares
       the browser's real `https://...` Origin header against a same-origin
       URL it computes as `http://...`, and rejects the mismatch ("Origin
       checking failed"). This is the same setting the platform's own
       core/settings/prod.py already relies on for itself.

    Neither override fires if the student's own settings.py already set it —
    this file is regenerated on every deploy and never touches their actual
    settings.py.
    """
    module_path, _, attr = wsgi_target.partition(':')
    attr = attr or 'application'
    wrapper_path = project_dir / f'{_PLATFORM_WSGI_WRAPPER_NAME}.py'
    wrapper_path.write_text(
        '"""Auto-generated by the platform on every deploy — do not edit, it will be overwritten."""\n'
        'import os\n'
        f'os.environ.setdefault("DJANGO_SETTINGS_MODULE", {settings_module!r})\n'
        'import django\n'
        'django.setup()\n'
        'from django.conf import settings as _settings\n'
        'if "*" not in _settings.ALLOWED_HOSTS:\n'
        '    _settings.ALLOWED_HOSTS = [*_settings.ALLOWED_HOSTS, "*"]\n'
        'if not getattr(_settings, "SECURE_PROXY_SSL_HEADER", None):\n'
        '    _settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")\n'
        f'from {module_path} import {attr} as {attr}  # noqa: F401\n'
    )
    return f'{_PLATFORM_WSGI_WRAPPER_NAME}:{attr}'


def _stop_proc(project_id: int) -> None:
    with _lock:
        proc = _procs.pop(project_id, None)
    if proc is not None:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=8)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
        log.info('Stopped project %s (was pid %s)', project_id, proc.pid)
    # Always remove from state file, even if proc wasn't tracked in memory
    _remove_from_state(project_id)


_BASE_PACKAGES = {
    'flask':  ['flask', 'gunicorn'],
    # psycopg2-binary + django-environ are pre-installed so settings.py can do
    # `DATABASES = {'default': env.db('DATABASE_URL')}` without adding either
    # to requirements.txt — the platform always injects a Postgres DATABASE_URL.
    'django': ['django', 'gunicorn', 'psycopg2-binary', 'django-environ'],
}

# A plain requirements.txt at the root is the common case, but splitting
# requirements into a requirements/ directory (base/prod/dev) is a very common,
# legitimate Django convention too — pip resolves `-r base.txt` references
# inside these files relative to the including file's own directory, so just
# pointing pip at the right one handles the whole chain. Checked in order;
# first match wins. Production-leaning names are preferred over dev/local ones
# since this is always a production deploy.
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


def _find_requirements_file(project_dir: Path) -> Path | None:
    for candidate in _REQUIREMENTS_CANDIDATES:
        p = project_dir / candidate
        if p.is_file():
            return p
    return None


def _setup_venv(project_id: int, project_type: str = 'flask') -> tuple[bool, str]:
    """Create venv if missing, then pip install the framework baseline + requirements.txt."""
    project_dir = _project_dir(project_id)
    venv_dir = project_dir / '.venv'

    if not venv_dir.exists():
        log.info('Creating venv for project %s', project_id)
        venv.create(str(venv_dir), with_pip=True)

    pip = _venv_bin(project_id, 'pip')
    base_packages = _BASE_PACKAGES.get(project_type, _BASE_PACKAGES['flask'])

    try:
        r = subprocess.run(
            [str(pip), 'install', '--quiet', *base_packages],
            capture_output=True, text=True, timeout=PIP_TIMEOUT,
        )
        if r.returncode != 0:
            return False, f'pip base install failed: {_tail(r.stderr)}'
    except subprocess.TimeoutExpired:
        return False, 'pip install timed out (base packages)'

    req = _find_requirements_file(project_dir)
    if req:
        try:
            r = subprocess.run(
                [str(pip), 'install', '--quiet', '-r', str(req)],
                capture_output=True, text=True, timeout=PIP_TIMEOUT,
            )
            if r.returncode != 0:
                return False, f'pip install failed ({req.relative_to(project_dir)}): {_tail(r.stderr)}'
        except subprocess.TimeoutExpired:
            return False, f'pip install timed out ({req.relative_to(project_dir)})'

    return True, ''


def _run_django_management(project_id: int, extra_env: dict[str, str]) -> tuple[bool, str]:
    """Run `manage.py migrate` (fatal on failure) then `collectstatic` (best-effort).
    `extra_env` must include DJANGO_SETTINGS_MODULE and (normally) DATABASE_URL."""
    project_dir = _project_dir(project_id)
    python = _venv_bin(project_id, 'python')
    env = _student_env(project_dir, extra_env)

    try:
        r = subprocess.run(
            [str(python), 'manage.py', 'migrate', '--noinput'],
            cwd=str(project_dir), env=env,
            capture_output=True, text=True, timeout=DJANGO_MANAGE_TIMEOUT,
        )
        if r.returncode != 0:
            return False, f'manage.py migrate failed: {_tail(r.stderr) or _tail(r.stdout)}'
    except subprocess.TimeoutExpired:
        return False, 'manage.py migrate timed out'

    try:
        r = subprocess.run(
            [str(python), 'manage.py', 'collectstatic', '--noinput'],
            cwd=str(project_dir), env=env,
            capture_output=True, text=True, timeout=DJANGO_MANAGE_TIMEOUT,
        )
        if r.returncode != 0:
            log.warning('Project %s: collectstatic skipped/failed: %s', project_id, _tail(r.stderr))
    except subprocess.TimeoutExpired:
        log.warning('Project %s: collectstatic timed out', project_id)

    return True, ''


# ── endpoints ─────────────────────────────────────────────────────────────────

@management_app.get('/health')
def health():
    running = sum(1 for p in _procs.values() if p.poll() is None)
    return jsonify({'status': 'ok', 'running': running, 'total': len(_procs)})


@management_app.post('/deploy/<int:project_id>')
def deploy(project_id: int):
    data = request.get_json(force=True) or {}
    port = data.get('port')
    project_type = data.get('project_type', 'flask')
    posted_env = data.get('env') or {}
    if not port:
        return jsonify({'error': 'port is required'}), 400

    project_dir = _project_dir(project_id)
    if not project_dir.exists():
        return jsonify({'error': 'project directory not found'}), 404

    # Stop any existing process before reinstalling/restarting
    _stop_proc(project_id)

    extra_env: dict[str, str] = dict(posted_env)
    if project_type == 'django':
        django_info = _detect_django_entry(project_dir)
        if not django_info:
            return jsonify({
                'error': (
                    'No Django entry point found. '
                    'Create manage.py at the ZIP root (standard `django-admin startproject` layout).'
                )
            }), 400
        settings_module, entry = django_info
        extra_env['DJANGO_SETTINGS_MODULE'] = settings_module
    else:
        entry = _detect_entry(project_dir)
        if not entry:
            return jsonify({
                'error': (
                    'No Flask entry point found. '
                    'Create app.py with: app = Flask(__name__)'
                )
            }), 400

    ok, err = _setup_venv(project_id, project_type)
    if not ok:
        log.error('venv setup failed for project %s: %s', project_id, err)
        return jsonify({'error': err, 'status': 'install_failed'}), 500

    if project_type == 'django':
        ok, err = _run_django_management(project_id, extra_env)
        if not ok:
            log.error('manage.py step failed for project %s: %s', project_id, err)
            return jsonify({'error': err, 'status': 'migrate_failed'}), 500
        entry = _write_platform_wsgi_wrapper(project_dir, extra_env['DJANGO_SETTINGS_MODULE'], entry)

    gunicorn = _venv_bin(project_id, 'gunicorn')
    env = _student_env(project_dir, extra_env)

    try:
        proc = subprocess.Popen(
            [
                str(gunicorn),
                '-b', f'0.0.0.0:{port}',
                '--workers', '1',
                '--threads', '2',
                '--timeout', str(GUNICORN_TIMEOUT),
                '--access-logfile', '-',
                '--error-logfile', '-',
                entry,
            ],
            cwd=str(project_dir),
            env=env,
        )
    except OSError as exc:
        return jsonify({'error': str(exc)}), 500

    with _lock:
        _procs[project_id] = proc

    # Persist port + type + env so we can restore after a container restart
    _save_state_with_port(project_id, port, project_type, extra_env)

    log.info('Started project %s  type=%s  entry=%s  port=%s  pid=%s', project_id, project_type, entry, port, proc.pid)
    return jsonify({'status': 'started', 'pid': proc.pid, 'port': port, 'entry': entry})


_SUPERUSER_SCRIPT = """
import os, django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
raw_username = os.environ['PLATFORM_SU_USERNAME']
email = os.environ.get('PLATFORM_SU_EMAIL', '')
password = os.environ['PLATFORM_SU_PASSWORD']
field = User.USERNAME_FIELD
# A lot of real Django projects use the email address as the login
# identifier even though USERNAME_FIELD is still the plain default
# 'username' (a very common custom-login-form pattern) -- the value that
# actually has to be stored in that field is whatever the project's login
# page asks for, which in that case IS the email. If we stored a
# separately-typed "username" there instead, the account gets created
# fine but can never log in: the identifier we tell the operator to type
# and the one actually saved silently diverge. So whenever an email is
# given, it IS the identifier -- not a second, independent value.
identifier = email or raw_username
user, created = User.objects.get_or_create(**{field: identifier})
if email and field != 'email':
    user.email = email
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()
# If the app uses django-axes (brute-force login lockout), a reset must also
# clear any existing lockout for this identifier -- otherwise a perfectly
# valid new password still fails to log in, silently, for up to the
# lockout window.
try:
    from axes.utils import reset as axes_reset
    axes_reset(username=identifier)
except Exception:
    pass
print('created' if created else 'updated')
"""


@management_app.post('/django_superuser/<int:project_id>')
def django_superuser(project_id: int):
    """Create or reset a Django superuser directly in the project's own database."""
    data = request.get_json(force=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()
    posted_env = data.get('env') or {}
    if not username or not password:
        return jsonify({'error': 'username and password are required'}), 400

    project_dir = _project_dir(project_id)
    if not project_dir.exists() or not (project_dir / '.venv').exists():
        return jsonify({'error': 'Deploy this app at least once before setting a superadmin.'}), 400

    django_info = _detect_django_entry(project_dir)
    if not django_info:
        return jsonify({'error': 'No Django entry point found.'}), 400
    settings_module, _entry = django_info

    python = _venv_bin(project_id, 'python')
    env = _student_env(project_dir, {
        **posted_env,
        'DJANGO_SETTINGS_MODULE': settings_module,
        'PLATFORM_SU_USERNAME': username,
        'PLATFORM_SU_EMAIL': email,
        'PLATFORM_SU_PASSWORD': password,
    })

    try:
        r = subprocess.run(
            [str(python), '-c', _SUPERUSER_SCRIPT],
            cwd=str(project_dir), env=env,
            capture_output=True, text=True, timeout=DJANGO_MANAGE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Operation timed out.'}), 500

    if r.returncode != 0:
        return jsonify({'error': _tail(r.stderr) or _tail(r.stdout) or 'Unknown error'}), 500

    action = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'updated'
    log.info('Superuser %s for project %s: %s', action, project_id, username)
    return jsonify({'status': 'ok', 'action': action, 'username': username})


_DB_ENGINE_SCRIPT = """
import os, django
django.setup()
from django.conf import settings
db = settings.DATABASES.get('default', {})
print(db.get('ENGINE', ''))
print(db.get('HOST', ''))
print(db.get('NAME', ''))
"""


@management_app.get('/audit/db_engines')
def audit_db_engines():
    """
    For every Django project this runner knows about, report which database
    engine its own settings.py actually resolved to at runtime -- not just
    whether the platform injected a Postgres DATABASE_URL, but whether the
    project's settings.py actually reads it. A project whose settings.py
    ignores DATABASE_URL silently falls back to sqlite3, which loses all
    data on every redeploy (the site dir, sqlite file included, is wiped
    and re-extracted each time).
    """
    try:
        saved: dict[str, object] = json.loads(_STATE_FILE.read_text()) if _STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        saved = {}

    results: dict[str, dict] = {}
    for pid_str, value in saved.items():
        if not isinstance(value, dict) or value.get('type') != 'django':
            continue
        try:
            project_id = int(pid_str)
        except ValueError:
            continue

        project_dir = _project_dir(project_id)
        if not project_dir.exists() or not (project_dir / '.venv').exists():
            results[pid_str] = {'error': 'project dir or venv missing'}
            continue

        django_info = _detect_django_entry(project_dir)
        if not django_info:
            results[pid_str] = {'error': 'no Django entry point found'}
            continue
        settings_module, _entry = django_info

        extra_env = dict(value.get('env') or {})
        extra_env['DJANGO_SETTINGS_MODULE'] = settings_module
        python = _venv_bin(project_id, 'python')
        env = _student_env(project_dir, extra_env)

        try:
            r = subprocess.run(
                [str(python), '-c', _DB_ENGINE_SCRIPT],
                cwd=str(project_dir), env=env,
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            results[pid_str] = {'error': 'timed out'}
            continue

        if r.returncode != 0:
            results[pid_str] = {'error': _tail(r.stderr) or _tail(r.stdout) or 'unknown error'}
            continue

        lines = r.stdout.strip().splitlines()
        engine = lines[0] if len(lines) > 0 else ''
        host = lines[1] if len(lines) > 1 else ''
        name = lines[2] if len(lines) > 2 else ''
        results[pid_str] = {
            'engine': engine,
            'host': host,
            'name': name,
            'is_postgres': 'postgresql' in engine or 'postgis' in engine,
        }

    return jsonify(results)


@management_app.post('/stop/<int:project_id>')
def stop_project(project_id: int):
    _stop_proc(project_id)
    return jsonify({'status': 'stopped'})


@management_app.get('/status/<int:project_id>')
def status(project_id: int):
    with _lock:
        proc = _procs.get(project_id)
    if proc is None:
        return jsonify({'status': 'not_running'})
    rc = proc.poll()
    if rc is None:
        return jsonify({'status': 'running', 'pid': proc.pid})
    return jsonify({'status': 'exited', 'returncode': rc, 'pid': proc.pid})


@management_app.get('/list')
def list_projects():
    result = {}
    with _lock:
        snapshot = dict(_procs)
    for pid, proc in snapshot.items():
        rc = proc.poll()
        result[pid] = 'running' if rc is None else f'exited({rc})'
    return jsonify(result)


if __name__ == '__main__':
    if not API_TOKEN or API_TOKEN == 'change-me-strong-random-token':
        log.error(
            'FLASK_RUNNER_TOKEN is not set or uses the default placeholder. '
            'Set a strong random token before running in production.'
        )
        sys.exit(1)
    log.info('App Runner starting on :6000 (flask + django)  sites_root=%s', SITES_ROOT)
    _restore_state()
    management_app.run(host='0.0.0.0', port=6000, debug=False)
