"""
Containers Runner — sole owner of /var/run/docker.sock on this host.
Exposes a JSON HTTP API on port 6100 (internal Docker network only) for provisioning
per-project WordPress/PHP/Drupal app containers and their per-project MySQL
containers. Django/Celery (apps/containers/services.py) never touches the Docker
socket directly — this process is the only one that does. See php.txt section 3,
INF-1, and section 10 decision 1.
"""
from __future__ import annotations

import logging
import os
import sys

import docker
from docker.errors import APIError, NotFound
from flask import Flask, jsonify, request

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [containers-runner] %(message)s',
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

management_app = Flask(__name__)

API_TOKEN = os.environ.get('CONTAINERS_RUNNER_TOKEN', '')
PLATFORM_NETWORK = os.environ.get('PLATFORM_DOCKER_NETWORK', 'platform_net')
EXEC_TIMEOUT = int(os.environ.get('EXEC_TIMEOUT', '300'))
MAX_EXEC_OUTPUT = 8000

client = docker.from_env()


# ── auth ──────────────────────────────────────────────────────────────────────

@management_app.before_request
def _auth():
    if request.path == '/health':
        return None
    if API_TOKEN and request.headers.get('X-Runner-Token') != API_TOKEN:
        return jsonify({'error': 'unauthorized'}), 401


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_container(name: str):
    try:
        return client.containers.get(name)
    except NotFound:
        return None


def _remove_named_volumes(name: str) -> None:
    """Remove volumes whose name starts with '{name}_' — the convention this runner
    uses for a container's own data volumes (e.g. 'proj_5_mysql_data')."""
    prefix = f'{name}_'
    try:
        for vol in client.volumes.list():
            if vol.name.startswith(prefix):
                try:
                    vol.remove(force=True)
                except APIError as exc:
                    log.warning('Could not remove volume %s: %s', vol.name, exc)
    except APIError as exc:
        log.warning('Could not list volumes while cleaning up %s: %s', name, exc)


# ── endpoints ─────────────────────────────────────────────────────────────────

@management_app.get('/health')
def health():
    try:
        client.ping()
        return jsonify({'status': 'ok'})
    except APIError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 503


@management_app.post('/containers/<name>')
def create_or_replace(name: str):
    """Create (replacing any existing container of the same name) and start it."""
    data = request.get_json(force=True) or {}
    image = data.get('image')
    if not image:
        return jsonify({'error': 'image is required'}), 400

    env = data.get('env') or {}
    volumes_in = data.get('volumes') or {}
    mem_limit = data.get('mem_limit')
    nano_cpus = data.get('nano_cpus')
    command = data.get('command')

    volumes = {
        f'{name}_{vol_key}' if not vol_key.startswith(name) else vol_key: {'bind': path, 'mode': 'rw'}
        for vol_key, path in volumes_in.items()
    }

    existing = _get_container(name)
    if existing is not None:
        try:
            existing.remove(force=True)
        except APIError as exc:
            return jsonify({'error': f'could not remove existing container: {exc}'}), 500

    run_kwargs = dict(
        image=image,
        name=name,
        detach=True,
        restart_policy={'Name': 'unless-stopped'},
        environment=env,
        volumes=volumes,
        network=PLATFORM_NETWORK,
    )
    if mem_limit:
        run_kwargs['mem_limit'] = mem_limit
    if nano_cpus:
        run_kwargs['nano_cpus'] = int(nano_cpus)
    if command:
        run_kwargs['command'] = command

    try:
        container = client.containers.run(**run_kwargs)
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500

    log.info('Started container %s (image=%s)', name, image)
    return jsonify({'status': 'started', 'id': container.id})


@management_app.post('/containers/<name>/stop')
def stop(name: str):
    container = _get_container(name)
    if container is None:
        return jsonify({'status': 'not_found'})
    try:
        container.stop(timeout=15)
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500
    return jsonify({'status': 'stopped'})


@management_app.post('/containers/<name>/start')
def start(name: str):
    """Start an already-created (but stopped) container — never recreates."""
    container = _get_container(name)
    if container is None:
        return jsonify({'error': 'not_found'}), 404
    try:
        container.start()
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500
    return jsonify({'status': 'started'})


@management_app.delete('/containers/<name>')
def remove(name: str):
    container = _get_container(name)
    remove_volumes = request.args.get('remove_volumes', '').lower() == 'true'
    if container is not None:
        try:
            container.remove(force=True)
        except APIError as exc:
            return jsonify({'error': str(exc)}), 500
    if remove_volumes:
        _remove_named_volumes(name)
    if container is None:
        return jsonify({'status': 'not_found'})
    return jsonify({'status': 'removed'})


@management_app.post('/containers/<name>/upload')
def upload_archive(name: str):
    """Extract a tar archive (raw bytes request body) into an already-running
    container at ?path= (default /var/www/html). Used to deploy PHP/Drupal site
    files into a project's own named volume without ever giving Django/worker
    direct filesystem access to it — see php.txt section 5 deviation note."""
    container = _get_container(name)
    if container is None:
        return jsonify({'error': 'not_found'}), 404
    dest = request.args.get('path', '/var/www/html')
    data = request.get_data()
    if not data:
        return jsonify({'error': 'empty archive'}), 400
    try:
        ok = container.put_archive(dest, data)
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500
    if not ok:
        return jsonify({'error': 'put_archive failed'}), 500
    return jsonify({'status': 'uploaded'})


@management_app.get('/containers/<name>/status')
def status(name: str):
    container = _get_container(name)
    if container is None:
        return jsonify({'status': 'not_running'})
    container.reload()
    return jsonify({'status': container.status})


@management_app.get('/containers/<name>/stats')
def stats(name: str):
    """Point-in-time mem/cpu usage — php.txt Phase 5, BIL-2. Not a time series; the
    caller polls this if it wants a trend."""
    container = _get_container(name)
    if container is None:
        return jsonify({'status': 'not_running'})
    container.reload()
    if container.status != 'running':
        return jsonify({'status': container.status})
    try:
        raw = container.stats(stream=False)
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500

    mem = raw.get('memory_stats', {})
    mem_usage = mem.get('usage', 0)
    mem_limit = mem.get('limit', 0)

    cpu = raw.get('cpu_stats', {})
    precpu = raw.get('precpu_stats', {})
    cpu_total = cpu.get('cpu_usage', {}).get('total_usage', 0)
    precpu_total = precpu.get('cpu_usage', {}).get('total_usage', 0)
    system_cpu = cpu.get('system_cpu_usage', 0)
    presystem_cpu = precpu.get('system_cpu_usage', 0)
    online_cpus = cpu.get('online_cpus') or len(cpu.get('cpu_usage', {}).get('percpu_usage') or [1])

    cpu_delta = cpu_total - precpu_total
    system_delta = system_cpu - presystem_cpu
    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0 if system_delta > 0 and cpu_delta > 0 else 0.0

    return jsonify({
        'status': 'running',
        'mem_usage_mb': round(mem_usage / (1024 * 1024), 1),
        'mem_limit_mb': round(mem_limit / (1024 * 1024), 1),
        'cpu_percent': round(cpu_percent, 1),
    })


@management_app.post('/containers/<name>/exec')
def exec_cmd(name: str):
    """Run a one-off command in an already-running container (composer install, drush, wp-cli)."""
    data = request.get_json(force=True) or {}
    cmd = data.get('cmd')
    if not cmd:
        return jsonify({'error': 'cmd is required'}), 400
    container = _get_container(name)
    if container is None:
        return jsonify({'error': 'not_found'}), 404
    try:
        result = container.exec_run(cmd, demux=False)
    except APIError as exc:
        return jsonify({'error': str(exc)}), 500
    output = result.output.decode(errors='replace') if result.output else ''
    return jsonify({'exit_code': result.exit_code, 'output': output[-MAX_EXEC_OUTPUT:]})


if __name__ == '__main__':
    if not API_TOKEN or API_TOKEN == 'change-me-strong-random-token':
        log.error(
            'CONTAINERS_RUNNER_TOKEN is not set or uses the default placeholder. '
            'Set a strong random token before running in production.'
        )
        sys.exit(1)
    log.info('Containers Runner starting on :6100  network=%s', PLATFORM_NETWORK)
    management_app.run(host='0.0.0.0', port=6100, debug=False)
