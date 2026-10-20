"""
Provision per-project PostgreSQL databases on the platform's shared Postgres
server (the same instance the platform's own DATABASE_URL points at).
Used by Django app deploys so student apps get Postgres instead of SQLite.
"""
from __future__ import annotations

import logging
import secrets

from django.conf import settings

from apps.databases.models import DatabaseInstance
from apps.projects.models import Project

log = logging.getLogger(__name__)

_IDENT_PREFIX = 'proj_'


def _db_identifier(project: Project) -> str:
    return f'{_IDENT_PREFIX}{project.pk}'


def _admin_dsn() -> dict:
    """Admin connection params for the shared Postgres server."""
    db = settings.DATABASES['default']
    return {
        'host': db.get('HOST') or 'localhost',
        'port': db.get('PORT') or 5432,
        'user': db['USER'],
        'password': db['PASSWORD'],
        'dbname': 'postgres',  # maintenance DB — needed to issue CREATE ROLE/DATABASE
    }


def _encrypt(value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(settings.FERNET_KEY).encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(settings.FERNET_KEY).decrypt(value.encode()).decode()


def get_or_provision_postgres_db(project: Project) -> DatabaseInstance:
    """
    Return this project's PostgreSQL DatabaseInstance, creating the role + database
    on first call. Idempotent — safe to call on every deploy/redeploy.
    """
    existing = DatabaseInstance.objects.filter(
        project=project, engine=DatabaseInstance.Engine.POSTGRES,
    ).first()
    if existing:
        return existing

    import psycopg2
    from psycopg2 import sql

    ident = _db_identifier(project)
    password = secrets.token_urlsafe(24)
    admin = _admin_dsn()

    conn = psycopg2.connect(**admin)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL('CREATE ROLE {} LOGIN PASSWORD %s').format(sql.Identifier(ident)),
                (password,),
            )
            cur.execute(
                sql.SQL('CREATE DATABASE {} OWNER {}').format(
                    sql.Identifier(ident), sql.Identifier(ident),
                )
            )
    finally:
        conn.close()

    return DatabaseInstance.objects.create(
        project=project,
        engine=DatabaseInstance.Engine.POSTGRES,
        name=ident,
        host=admin['host'],
        port=admin['port'],
        username=ident,
        password_encrypted=_encrypt(password),
    )


def database_url_for_instance(instance: DatabaseInstance) -> str:
    password = _decrypt(instance.password_encrypted)
    return f'postgres://{instance.username}:{password}@{instance.host}:{instance.port}/{instance.name}'


def database_env_vars_for_instance(instance: DatabaseInstance) -> dict[str, str]:
    """
    Every env var naming convention a Django project might reasonably use to
    pick up this database, injected automatically so the project owner never
    has to hand-copy credentials onto the Environment page themselves:
    - DATABASE_URL: the common django-environ / dj-database-url style DSN.
    - DATABASE_{URL_NAME,NAME,USER,PASSWORD,HOST,PORT}: discrete components,
      for settings.py written to read them individually instead of a DSN
      (seen in practice — a project's own prod.py required exactly these).
    - PG{DATABASE,USER,PASSWORD,HOST,PORT}: libpq's own standard env vars,
      which psycopg2 (and `psql`) honor natively with zero settings.py code.
    """
    password = _decrypt(instance.password_encrypted)
    port = str(instance.port)
    return {
        'DATABASE_URL': f'postgres://{instance.username}:{password}@{instance.host}:{port}/{instance.name}',
        'DATABASE_URL_NAME': instance.name,
        'DATABASE_NAME': instance.name,
        'DATABASE_USER': instance.username,
        'DATABASE_PASSWORD': password,
        'DATABASE_HOST': instance.host,
        'DATABASE_PORT': port,
        'PGDATABASE': instance.name,
        'PGUSER': instance.username,
        'PGPASSWORD': password,
        'PGHOST': instance.host,
        'PGPORT': port,
    }


def deprovision_postgres_db(project: Project) -> None:
    """Drop this project's database + role, if any. Safe to call even if never provisioned."""
    instance = DatabaseInstance.objects.filter(
        project=project, engine=DatabaseInstance.Engine.POSTGRES,
    ).first()
    if not instance:
        return

    import psycopg2
    from psycopg2 import sql

    admin = _admin_dsn()
    try:
        conn = psycopg2.connect(**admin)
    except psycopg2.OperationalError:
        log.exception('Could not reach Postgres to drop db for project %s', project.pk)
        return
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # FORCE (PG 13+) also terminates any lingering app connections.
            cur.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(instance.name)))
            cur.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(instance.username)))
    except psycopg2.Error:
        log.exception('Failed to drop postgres db/role for project %s', project.pk)
    finally:
        conn.close()
