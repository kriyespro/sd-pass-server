from .base import *  # noqa: F403, F405

DEBUG = False

DATABASES = {
    'default': env.db('DATABASE_URL'),  # noqa: F405
}

# Comma-separated in env: include your dashboard host, platform base domain, and every student custom host.
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])  # noqa: F405

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
