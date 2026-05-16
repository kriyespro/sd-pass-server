from .base import *  # noqa: F403, F405

DEBUG = False

_db = env.db('DATABASE_URL')  # noqa: F405
_db.setdefault('CONN_MAX_AGE', 60)   # reuse DB connection for 60 s per worker
_db.setdefault('CONN_HEALTH_CHECKS', True)
DATABASES = {'default': _db}

# Comma-separated in env: include your dashboard host, platform base domain, and every student custom host.
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])  # noqa: F405

# ── TLS / HTTPS ───────────────────────────────────────────────────────────────
# Defaults = real HTTPS behind nginx/Traefik. For bare HTTP (no TLS terminator)
# set SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
# SECURE_PROXY_SSL=False.
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)  # noqa: F405
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)  # noqa: F405
if env.bool('SECURE_PROXY_SSL', default=True):  # noqa: F405
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SECURE_PROXY_SSL_HEADER = None

USE_X_FORWARDED_HOST = env.bool('USE_X_FORWARDED_HOST', default=False)  # noqa: F405

ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'  # noqa: F405

# ── HSTS (enable after confirming all traffic is HTTPS) ───────────────────────
# 6 months in seconds — safe starting value. Raise to 31536000 (1 yr) once stable.
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=15768000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)  # noqa: F405
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)  # noqa: F405

# ── Security headers ──────────────────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# ── Session hardening ─────────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False   # Must remain False — JS needs to read the CSRF token

# Reload .jinja files from disk when templates are bind-mounted (docker-compose ./templates)
# Default False in prod for performance — set TEMPLATE_AUTO_RELOAD=True only for hot-reload dev stacks.
if env.bool('TEMPLATE_AUTO_RELOAD', default=False):  # noqa: F405
    TEMPLATES[0]['OPTIONS']['auto_reload'] = True  # noqa: F405
