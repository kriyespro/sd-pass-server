from .base import *  # noqa: F403, F405

DEBUG = False

_db = env.db('DATABASE_URL')  # noqa: F405
_db.setdefault('CONN_MAX_AGE', 60)   # reuse DB connection for 60 s per worker
_db.setdefault('CONN_HEALTH_CHECKS', True)
DATABASES = {'default': _db}

# Comma-separated in env: include your dashboard host, platform base domain, and every student custom host.
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])  # noqa: F405

# TLS behaviour (defaults = real HTTPS behind nginx). For direct HTTP to Gunicorn
# (e.g. http://IP:9898 with no TLS terminator), set all *_False and SECURE_PROXY_SSL=False.
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)  # noqa: F405
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)  # noqa: F405
if env.bool('SECURE_PROXY_SSL', default=True):  # noqa: F405
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SECURE_PROXY_SSL_HEADER = None

USE_X_FORWARDED_HOST = env.bool('USE_X_FORWARDED_HOST', default=False)  # noqa: F405
