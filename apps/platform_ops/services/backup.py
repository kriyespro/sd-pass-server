from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import zipfile
from shutil import which
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.platform_ops.models import PlatformBackup
from apps.platform_ops.utils import format_bytes

logger = logging.getLogger(__name__)


def backup_root() -> Path:
    root = Path(getattr(settings, 'PLATFORM_BACKUP_ROOT', settings.BASE_DIR / 'data' / 'platform_backups'))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _pg_dump_executable() -> str:
    for candidate in ('pg_dump-16', 'pg_dump'):
        path = which(candidate)
        if path:
            return path
    raise RuntimeError(
        'pg_dump not found. Rebuild the Docker image (postgresql-client-16 required).'
    )


def _safe_name(backup: PlatformBackup) -> str:
    ts = backup.created_at.strftime('%Y%m%d-%H%M%S')
    return f'platform-{backup.backup_type}-{ts}-{backup.pk}.zip'


def _dump_database(work_dir: Path) -> Path | None:
    db = settings.DATABASES['default']
    engine = db.get('ENGINE', '')
    dest = work_dir / 'database'
    dest.mkdir(parents=True, exist_ok=True)

    if 'postgresql' in engine:
        sql_path = dest / 'postgresql.sql'
        env = os.environ.copy()
        password = db.get('PASSWORD') or ''
        if password:
            env['PGPASSWORD'] = password
        cmd = [
            _pg_dump_executable(),
            '-h', db.get('HOST') or 'localhost',
            '-p', str(db.get('PORT') or 5432),
            '-U', db.get('USER') or 'postgres',
            '-d', db['NAME'],
            '-f', str(sql_path),
            '--no-owner',
            '--no-acl',
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or 'pg_dump failed').strip()
            raise RuntimeError(err[:2000])
        if not sql_path.is_file() or sql_path.stat().st_size == 0:
            raise RuntimeError('pg_dump produced an empty file')
        return sql_path

    if 'sqlite' in engine:
        src = Path(db['NAME'])
        if not src.is_file():
            raise FileNotFoundError(f'SQLite database not found: {src}')
        out = dest / 'sqlite3.db'
        shutil.copy2(src, out)
        return out

    raise RuntimeError(f'Unsupported database engine: {engine}')


def _copy_sites(work_dir: Path) -> Path | None:
    sites_root = Path(settings.STUDENT_SITE_ROOT)
    if not sites_root.is_dir():
        return None
    dest = work_dir / 'sites'
    shutil.copytree(sites_root, dest, dirs_exist_ok=True)
    return dest


def create_platform_backup(*, backup_id: int) -> PlatformBackup:
    backup = PlatformBackup.objects.get(pk=backup_id)
    backup.status = PlatformBackup.Status.RUNNING
    backup.save(update_fields=['status'])

    work_dir = backup_root() / f'_work_{backup.pk}'
    zip_path = backup_root() / _safe_name(backup)

    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        includes_db = backup.backup_type in (
            PlatformBackup.BackupType.FULL,
            PlatformBackup.BackupType.DATABASE,
        )
        includes_sites = backup.backup_type in (
            PlatformBackup.BackupType.FULL,
            PlatformBackup.BackupType.SITES,
        )
        backup.includes_database = includes_db
        backup.includes_sites = includes_sites

        db_file = _dump_database(work_dir) if includes_db else None
        sites_dir = _copy_sites(work_dir) if includes_sites else None

        manifest = {
            'backup_type': backup.backup_type,
            'created_at': timezone.now().isoformat(),
            'includes_database': includes_db,
            'includes_sites': includes_sites,
            'database_file': str(db_file.relative_to(work_dir)) if db_file else None,
            'sites_dir': 'sites' if sites_dir else None,
        }
        (work_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2),
            encoding='utf-8',
        )

        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for path in work_dir.rglob('*'):
                if path.is_file():
                    zf.write(path, path.relative_to(work_dir).as_posix())

        backup.storage_path = str(zip_path)
        backup.size_bytes = zip_path.stat().st_size
        backup.status = PlatformBackup.Status.DONE
        backup.finished_at = timezone.now()
        backup.save()
        logger.info(
            'platform_ops: backup #%s done — %s (%s)',
            backup.pk,
            zip_path.name,
            format_bytes(backup.size_bytes),
        )
    except Exception as exc:
        logger.exception('platform_ops: backup #%s failed', backup.pk)
        backup.status = PlatformBackup.Status.FAILED
        backup.finished_at = timezone.now()
        backup.error_message = str(exc)[:2000]
        backup.save()
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return backup


def resolve_backup_path(backup: PlatformBackup) -> Path:
    path = Path(backup.storage_path).resolve()
    root = backup_root().resolve()
    if not str(path).startswith(str(root)):
        raise ValueError('Invalid backup path')
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def delete_platform_backup(*, backup_id: int) -> None:
    """Remove backup ZIP from disk (if any) and delete the DB row."""
    backup = PlatformBackup.objects.get(pk=backup_id)
    if backup.status in (
        PlatformBackup.Status.PENDING,
        PlatformBackup.Status.RUNNING,
    ):
        raise RuntimeError('Cannot delete a backup that is still in progress.')

    if backup.storage_path:
        try:
            path = resolve_backup_path(backup)
            path.unlink(missing_ok=True)
        except (ValueError, FileNotFoundError):
            pass

    backup.delete()
    logger.info('platform_ops: deleted backup #%s', backup_id)
