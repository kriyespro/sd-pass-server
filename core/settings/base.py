"""
Shared Django settings for StudentCloud Deploy.
"""
import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

if os.path.isfile(BASE_DIR / '.env'):
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-set-secret-key-in-env')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
DEBUG = False

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'apps.accounts',
    'apps.students',
    'apps.projects',
    'apps.uploads',
    'apps.security',
    'apps.envmanager',
    'apps.deployments',
    'apps.domains',
    'apps.dnsmanager',
    'apps.sslmanager',
    'apps.logs',
    'apps.quotas',
    'apps.databases',
    'apps.backups',
    'apps.notifications',
    'apps.dashboard',
    'rest_framework',
    'rest_framework.authtoken',
    'apps.billing',
    'apps.api',
]

MIDDLEWARE = [
    'core.middleware.student_https_proto.StudentTraefikHttpsProtoMiddleware',
    'core.middleware.normalize_forwarded_host.NormalizeForwardedHostMiddleware',
    'core.middleware.recover_proxy_host.RecoverProxyHostMiddleware',
    'core.middleware.dynamic_allowed_hosts.DynamicAllowedHostsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.student_static_site.StudentStaticSiteMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'core.urls'

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
    'student_uploads': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
        'OPTIONS': {'location': str(BASE_DIR / 'data' / 'uploads')},
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

STUDENT_UPLOAD_ROOT = Path(
    env('STUDENT_UPLOAD_ROOT', default=str(BASE_DIR / 'data' / 'uploads'))
)
STUDENT_UPLOAD_MAX_BYTES = env.int('STUDENT_UPLOAD_MAX_BYTES', default=200 * 1024 * 1024)
# Django default is 2.5 MiB; larger multipart bodies raise RequestDataTooBig before the view runs.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int(
    'DATA_UPLOAD_MAX_MEMORY_SIZE',
    default=STUDENT_UPLOAD_MAX_BYTES + 8 * 1024 * 1024,
)

_fernet_raw = env('FERNET_KEY', default='')
if _fernet_raw:
    FERNET_KEY = _fernet_raw.encode()
else:
    import base64
    import hashlib

    FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())

CLAMD_UNIX_SOCKET = env('CLAMD_UNIX_SOCKET', default='')

STORAGES['student_uploads']['OPTIONS']['location'] = str(STUDENT_UPLOAD_ROOT)

STUDENT_SITE_ROOT = Path(
    env('STUDENT_SITE_ROOT', default=str(BASE_DIR / 'data' / 'sites'))
)

STUDENT_APPS_BASE_DOMAIN = env(
    'STUDENT_APPS_BASE_DOMAIN',
    default='apps.localhost',
)
# When True, Host matching *.STUDENT_APPS_BASE_DOMAIN gets X-Forwarded-Proto=https before
# SecurityMiddleware (TLS at nginx; Traefik→Gunicorn is HTTP). Requires public student URLs to be HTTPS.
STUDENT_TRUST_TRAEFIK_HTTPS = env.bool('STUDENT_TRUST_TRAEFIK_HTTPS', default=False)
# docker-compose.prod.yml only defines Traefik entrypoint "web" (:80 → host TRAEFIK_HTTP_PUBLISH).
# Default must match that. Use TRAEFIK_ENTRYPOINTS=websecure only if your Traefik static config adds it.
_STUDENT_APPS_LOCAL = STUDENT_APPS_BASE_DOMAIN.rstrip('.').endswith('.localhost')
TRAEFIK_DYNAMIC_DIR = Path(
    env('TRAEFIK_DYNAMIC_DIR', default=str(BASE_DIR / 'data' / 'traefik' / 'dynamic'))
)
TRAEFIK_CERT_RESOLVER = env('TRAEFIK_CERT_RESOLVER', default='letsencrypt')
TRAEFIK_ENTRYPOINTS = env.list(
    'TRAEFIK_ENTRYPOINTS',
    default=['web'],
)
TRAEFIK_TLS_ON_PROJECT_ROUTES = env.bool(
    'TRAEFIK_TLS_ON_PROJECT_ROUTES',
    default=False,
)
TRAEFIK_UPSTREAM_URL = env(
    'TRAEFIK_UPSTREAM_URL',
    default='http://127.0.0.1:8000',
)
STUDENT_PUBLIC_HTTP_PORT = env.int(
    'STUDENT_PUBLIC_HTTP_PORT',
    default=8000 if _STUDENT_APPS_LOCAL else 0,
)
# Optional port appended to {subdomain}.{STUDENT_APPS_BASE_DOMAIN} links only (e.g. 9080 for Traefik).
STUDENT_SITE_HTTP_PORT = env.int('STUDENT_SITE_HTTP_PORT', default=0)
# Scheme for dashboard / notification links to student sites (http or https).
STUDENT_SITE_PUBLIC_SCHEME = env(
    'STUDENT_SITE_PUBLIC_SCHEME',
    default='http',
).strip().rstrip(':').lower() or 'http'
if STUDENT_SITE_PUBLIC_SCHEME not in ('http', 'https'):
    STUDENT_SITE_PUBLIC_SCHEME = 'http'

CLOUDFLARE_API_TOKEN = env('CLOUDFLARE_API_TOKEN', default='')
CLOUDFLARE_ZONE_ID = env('CLOUDFLARE_ZONE_ID', default='')
PLATFORM_PUBLIC_IP = env('PLATFORM_PUBLIC_IP', default='')

# When True: if Host is 127.0.0.1/localhost but X-Forwarded-Host matches ALLOWED_HOSTS,
# rewrite Host (fixes nginx omitting proxy_set_header Host). Only safe if Gunicorn is
# bound to 127.0.0.1 (WEB_HTTP_BIND=127.0.0.1), not 0.0.0.0.
RECOVER_PROXY_HOST_FROM_FORWARDED = env.bool(
    'RECOVER_PROXY_HOST_FROM_FORWARDED',
    default=False,
)

LOG_RETENTION_DAYS = env.int('LOG_RETENTION_DAYS', default=7)

NOTIFICATION_RETENTION_DAYS = env.int('NOTIFICATION_RETENTION_DAYS', default=90)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'projects:dashboard'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'accounts:login'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool('CELERY_TASK_ALWAYS_EAGER', default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    'logs-delete-old-log-entries': {
        'task': 'logs.delete_old_log_entries',
        'schedule': crontab(hour=3, minute=5),
    },
    'quotas-snapshot-all-users': {
        'task': 'quotas.snapshot_all_users',
        'schedule': crontab(minute='*/15'),
    },
    'backups-run-scheduled': {
        'task': 'backups.run_scheduled_backups',
        'schedule': crontab(hour=4, minute=0),
    },
    'notifications-delete-old-read': {
        'task': 'notifications.delete_old_read_notifications',
        'schedule': crontab(hour=5, minute=10),
    },
    'domains-poll-custom-domain-verification': {
        'task': 'domains.poll_custom_domain_verification',
        'schedule': crontab(minute='*/5'),
    },
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.jinja2.Jinja2',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'environment': 'core.jinja2.environment',
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csrf',
                'core.context_processors.studentcloud_nav',
            ],
        },
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
