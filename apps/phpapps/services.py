"""
Generic PHP app provisioning (php.txt section 5 / section 9 Phase 3).

Deviation from php.txt's original "-v data/sites/<id>/:/var/www/html/" text: that
assumes a host bind-mount, which only exists in dev (docker-compose.yml's
./data/sites bind). docker-compose.prod.yml mounts /app/data/sites from a named
Docker volume (sites_data) instead, which containers_runner has no host path for —
you cannot bind-mount "a subdirectory of a named volume" into another container.
So PHP sites get their own per-project named volume, exactly like WordPress
(apps/wordpress/services.py) and MySQL (apps/containers/mysql.py): ZIP uploads are
extracted to a throwaway temp dir on the worker, tarred, and written into the
already-running app container's volume via containers_runner's put_archive endpoint
(apps.containers.services.upload_archive). This also keeps every project's files in
its own isolated volume instead of one shared tree every PHP container could reach.
"""
from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from apps.containers.mysql import create_mysql_db, drop_mysql_db
from apps.containers.services import (
    container_name,
    exec_in_container,
    remove_container,
    start_container,
    stop_container,
    upload_archive,
)
from apps.domains.services import remove_project_router_file, write_project_router_file
from apps.projects.models import Project, ProjectStatus

PHP_IMAGE = 'sd-pass/php-runtime:latest'  # built from deploy/php-runtime, see php.txt 5.1

# Same allow-list shape as apps/deployments/flask_deploy.py::FLASK_ALLOWED_SUFFIXES,
# PHP-flavored: adds .php/.phtml; composer.json/.lock and .env.example are allowed by
# filename below regardless of suffix.
PHP_ALLOWED_SUFFIXES = frozenset({
    '.php', '.phtml',
    '.html', '.htm', '.css', '.js', '.mjs', '.json',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.txt', '.md',
    '.cfg', '.ini', '.toml', '.yaml', '.yml',
    '.csv', '.xml', '.sql',
})
PHP_ALLOWED_FILENAMES = frozenset({'composer.json', 'composer.lock', '.env.example', '.htaccess'})

MAX_PHP_ZIP_SIZE = 80 * 1024 * 1024   # 80 MB
MAX_PHP_FILES = 3000

# Only DB_* keys the app's own .env.example already declares get overridden — never
# invented for apps that don't ask for them (php.txt section 5, provision() step 1).
_DB_ENV_KEYS = ('DB_CONNECTION', 'DB_HOST', 'DB_PORT', 'DB_DATABASE', 'DB_USERNAME', 'DB_PASSWORD')


def _is_ignored_entry(name: str) -> bool:
    """Same shape as flask_deploy._is_ignored_entry: skip __pycache__/macOS metadata."""
    parts = name.replace('\\', '/').split('/')
    return (
        '__pycache__' in parts
        or parts[0] == '__MACOSX'
        or any(p.startswith('._') for p in parts)
    )


def _validate_php_zip(zip_path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            entries = [i for i in zf.infolist() if not i.is_dir()]
            real_entries = [
                i for i in entries
                if not _is_ignored_entry((i.filename or '').replace('\\', '/').strip())
            ]
            if len(real_entries) > MAX_PHP_FILES:
                return False, f'ZIP contains {len(real_entries)} files (max {MAX_PHP_FILES})'
            total = 0
            for info in real_entries:
                name = (info.filename or '').replace('\\', '/').strip()
                if not name or name.startswith('/') or '..' in name.split('/'):
                    return False, f'Unsafe ZIP entry: {name!r}'
                base = Path(name).name.lower()
                suf = Path(name).suffix.lower()
                if suf not in PHP_ALLOWED_SUFFIXES and base not in PHP_ALLOWED_FILENAMES:
                    return False, (
                        f'File type not allowed: {name!r}. '
                        f'Allowed: PHP, HTML, CSS, JS, images, config, composer files.'
                    )
                total += info.file_size
                if total > MAX_PHP_ZIP_SIZE:
                    return False, f'ZIP contents exceed {MAX_PHP_ZIP_SIZE // 1024 // 1024} MB limit'
    except (OSError, zipfile.BadZipFile) as exc:
        return False, str(exc)
    return True, ''


def _extract_php_zip_to(zip_path: Path, dest: Path) -> None:
    """Same shape as flask_deploy._extract_flask_zip: strip one common root folder,
    skip macOS metadata, guard against path traversal."""
    root = dest.resolve()
    strip_prefix: str | None = None
    with zipfile.ZipFile(zip_path, 'r') as zf:
        parts_set: set[str] = set()
        has_root_level_file = False
        for info in zf.infolist():
            n = (info.filename or '').replace('\\', '/').strip().rstrip('/')
            if not n or _is_ignored_entry(n):
                continue
            parts = [p for p in n.split('/') if p]
            if len(parts) >= 2:
                parts_set.add(parts[0])
            elif not info.is_dir():
                # A real file sitting at the zip root (e.g. composer.json next to a
                # web/ or public/ dir) means this isn't a single-folder "compress
                # folder" wrapper — never strip in that case, or web/ would get
                # silently merged into the root alongside it.
                has_root_level_file = True
        if not has_root_level_file and len(parts_set) == 1:
            strip_prefix = parts_set.pop() + '/'

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            name = (info.filename or '').replace('\\', '/').strip()
            if not name or _is_ignored_entry(name):
                continue
            if strip_prefix and name.startswith(strip_prefix):
                name = name[len(strip_prefix):]
            if not name:
                continue
            is_dir = name.endswith('/') or info.is_dir()
            rel = Path(name)
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


def extract_php_zip(zip_path: Path) -> tuple[bool, str, Path | None]:
    """
    Validate + extract into a fresh temp dir (PHP sites live in a per-project Docker
    volume, not the shared host-bind-mounted data/sites tree — see module docstring).
    On success, caller owns the returned temp dir and must shutil.rmtree() it when done.
    """
    ok, err = _validate_php_zip(zip_path)
    if not ok:
        return False, err, None

    tmp_dir = Path(tempfile.mkdtemp(prefix='php_deploy_'))
    try:
        _extract_php_zip_to(zip_path, tmp_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False, f'ZIP extraction failed: {exc}', None
    return True, 'extracted_ok', tmp_dir


def detect_document_root(site_dir: Path) -> str:
    """'public' for CodeIgniter 4 / Laravel / Symfony's public/ convention, else the
    webroot itself (empty string)."""
    return 'public' if (site_dir / 'public' / 'index.php').is_file() else ''


def _build_tar(site_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tar:
        for entry in site_dir.rglob('*'):
            if entry.is_file():
                tar.add(entry, arcname=str(entry.relative_to(site_dir)))
    return buf.getvalue()


def _has_db_keys(example_text: str) -> bool:
    for line in example_text.splitlines():
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in _DB_ENV_KEYS:
                return True
    return False


def _merge_env_with_db(example_text: str, db: dict) -> str:
    values = {
        'DB_CONNECTION': 'mysql',
        'DB_HOST': db['host'],
        'DB_PORT': '3306',
        'DB_DATABASE': db['db'],
        'DB_USERNAME': db['user'],
        'DB_PASSWORD': db['password'],
    }
    out_lines = []
    for line in example_text.splitlines():
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in values:
                out_lines.append(f'{key}={values[key]}')
                continue
        out_lines.append(line)
    return '\n'.join(out_lines) + '\n'


def provision(project: Project, zip_path: Path) -> None:
    """
    1. Validate + extract ZIP to a temp dir, detect document root.
    2. If .env.example declares DB_* vars → create_mysql_db(project) and write a
       .env with just those keys filled in.
    3. Recreate the app container (named volume `proj_<id>_data`, reused across
       redeploys since removing a container doesn't remove its named volume), wipe
       its webroot, upload the new archive, composer install if composer.json exists.
    4. write_project_router_file(project); project.status = RUNNING.
    Called on every upload (first deploy and redeploys alike) — idempotent.
    """
    from apps.billing.services import docker_limits_for_project

    ok, msg, site_dir = extract_php_zip(zip_path)
    if not ok:
        raise RuntimeError(msg)

    try:
        env_example = site_dir / '.env.example'
        db = None
        if env_example.is_file():
            example_text = env_example.read_text(errors='replace')
            if _has_db_keys(example_text):
                db = create_mysql_db(project)
                (site_dir / '.env').write_text(_merge_env_with_db(example_text, db))

        docroot = detect_document_root(site_dir)
        app_name = container_name(project)
        limits = docker_limits_for_project(project)['app']

        env = {}
        if docroot:
            env['APACHE_DOCUMENT_ROOT'] = f'/var/www/html/{docroot}'

        started_ok, started_msg = start_container(
            app_name,
            image=PHP_IMAGE,
            env=env,
            volumes={'data': '/var/www/html'},
            mem_limit=limits['mem_limit'],
            nano_cpus=limits['nano_cpus'],
        )
        if not started_ok:
            if db is not None:
                drop_mysql_db(project)
            raise RuntimeError(f'PHP container provisioning failed for {app_name}: {started_msg}')

        # Clears the previous build's files on a redeploy; no-op on first deploy
        # (fresh empty volume).
        exec_in_container(app_name, ['find', '/var/www/html', '-mindepth', '1', '-delete'], timeout=30)

        tar_bytes = _build_tar(site_dir)
        up_ok, up_msg = upload_archive(app_name, tar_bytes, dest_path='/var/www/html')
        if not up_ok:
            raise RuntimeError(f'Uploading site files failed: {up_msg}')

        if (site_dir / 'composer.json').is_file():
            exec_in_container(
                app_name,
                ['composer', 'install', '--no-dev', '--no-interaction', '--working-dir=/var/www/html'],
                timeout=180,
            )

        write_project_router_file(project)
        Project.objects.filter(pk=project.pk).update(status=ProjectStatus.RUNNING)
    finally:
        shutil.rmtree(site_dir, ignore_errors=True)


def deprovision(project: Project) -> None:
    """Stop + remove the app container (with its volume), drop the MySQL container/DB
    if one was provisioned, and remove the Traefik route."""
    app_name = container_name(project)
    stop_container(app_name)
    remove_container(app_name, remove_volumes=True)
    drop_mysql_db(project)
    remove_project_router_file(project)
