"""
Flask App Runner — process manager for student Flask apps.
Exposes a JSON HTTP API on port 6000 (internal Docker network only).
Django/Celery calls this API to deploy, stop, and check app status.
"""
from __future__ import annotations

import json
import logging
import os
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

# State file lives one level above SITES_ROOT (still on the same volume).
_STATE_FILE = SITES_ROOT.parent / 'runner_state.json'

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
        SITES_ROOT.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(existing, indent=2))
    except OSError as exc:
        log.warning('Could not update runner state: %s', exc)


def _save_state_with_port(project_id: int, port: int) -> None:
    """Persist project_id→port mapping then write live state."""
    existing: dict[str, int] = {}
    try:
        existing = json.loads(_STATE_FILE.read_text()) if _STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        pass
    existing[str(project_id)] = port
    try:
        SITES_ROOT.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(existing, indent=2))
    except OSError as exc:
        log.warning('Could not save runner state: %s', exc)


def _restore_state() -> None:
    """On startup, re-launch gunicorn for every project saved in state file."""
    if not _STATE_FILE.exists():
        return
    try:
        saved: dict[str, int] = json.loads(_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning('Could not read runner state file: %s', exc)
        return

    if not saved:
        return

    log.info('Restoring %d Flask app(s) from state file', len(saved))
    for pid_str, port in saved.items():
        try:
            project_id = int(pid_str)
        except ValueError:
            continue
        project_dir = _project_dir(project_id)
        if not project_dir.exists():
            log.warning('Restore: project dir missing for %s — skipping', project_id)
            continue
        entry = _detect_entry(project_dir)
        if not entry:
            log.warning('Restore: no entry point for project %s — skipping', project_id)
            continue

        ok, err = _setup_venv(project_id)
        if not ok:
            log.error('Restore: venv setup failed for project %s: %s', project_id, err)
            continue

        gunicorn = _venv_bin(project_id, 'gunicorn')
        env = {**os.environ, 'PYTHONPATH': str(project_dir)}
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
        log.info('Restored project %s  entry=%s  port=%s  pid=%s', project_id, entry, port, proc.pid)


# ── helpers ───────────────────────────────────────────────────────────────────

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


def _setup_venv(project_id: int) -> tuple[bool, str]:
    """Create venv if missing, then pip install flask+gunicorn+requirements.txt."""
    project_dir = _project_dir(project_id)
    venv_dir = project_dir / '.venv'

    if not venv_dir.exists():
        log.info('Creating venv for project %s', project_id)
        venv.create(str(venv_dir), with_pip=True)

    pip = _venv_bin(project_id, 'pip')

    # Always ensure flask + gunicorn present
    try:
        r = subprocess.run(
            [str(pip), 'install', '--quiet', 'flask', 'gunicorn'],
            capture_output=True, text=True, timeout=PIP_TIMEOUT,
        )
        if r.returncode != 0:
            return False, f'pip base install failed: {r.stderr[:600]}'
    except subprocess.TimeoutExpired:
        return False, 'pip install timed out (base packages)'

    req = project_dir / 'requirements.txt'
    if req.exists():
        try:
            r = subprocess.run(
                [str(pip), 'install', '--quiet', '-r', str(req)],
                capture_output=True, text=True, timeout=PIP_TIMEOUT,
            )
            if r.returncode != 0:
                return False, f'pip requirements install failed: {r.stderr[:600]}'
        except subprocess.TimeoutExpired:
            return False, 'pip install timed out (requirements.txt)'

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
    if not port:
        return jsonify({'error': 'port is required'}), 400

    project_dir = _project_dir(project_id)
    if not project_dir.exists():
        return jsonify({'error': 'project directory not found'}), 404

    # Stop any existing process before reinstalling/restarting
    _stop_proc(project_id)

    ok, err = _setup_venv(project_id)
    if not ok:
        log.error('venv setup failed for project %s: %s', project_id, err)
        return jsonify({'error': err, 'status': 'install_failed'}), 500

    entry = _detect_entry(project_dir)
    if not entry:
        return jsonify({
            'error': (
                'No Flask entry point found. '
                'Create app.py with: app = Flask(__name__)'
            )
        }), 400

    gunicorn = _venv_bin(project_id, 'gunicorn')
    env = {**os.environ, 'PYTHONPATH': str(project_dir)}

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

    # Persist port so we can restore after a container restart
    _save_state_with_port(project_id, port)

    log.info('Started project %s  entry=%s  port=%s  pid=%s', project_id, entry, port, proc.pid)
    return jsonify({'status': 'started', 'pid': proc.pid, 'port': port, 'entry': entry})


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
    log.info('Flask Runner starting on :6000  sites_root=%s', SITES_ROOT)
    _restore_state()
    management_app.run(host='0.0.0.0', port=6000, debug=False)
