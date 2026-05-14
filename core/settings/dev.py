from .base import *  # noqa: F403, F405

DEBUG = True
ALLOWED_HOSTS = ['*']

database_url = env('DATABASE_URL', default='')
if database_url:
    DATABASES = {'default': env.db('DATABASE_URL')}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

CELERY_TASK_ALWAYS_EAGER = env.bool(
    'CELERY_TASK_ALWAYS_EAGER',
    default=True,
)

# Student apps on *.apps.localhost:8000 — extra trusted Origins for CSRF (wildcard entry).
if STUDENT_APPS_BASE_DOMAIN.rstrip('.').endswith('.localhost'):
    _base = STUDENT_APPS_BASE_DOMAIN.strip().strip('.')
    _csrf = list(CSRF_TRUSTED_ORIGINS)
    for _origin in (
        'http://127.0.0.1:8000',
        'http://localhost:8000',
        f'http://*.{_base}:8000',
        f'http://{_base}:8000',
    ):
        if _origin not in _csrf:
            _csrf.append(_origin)
    CSRF_TRUSTED_ORIGINS = _csrf

REST_FRAMEWORK = REST_FRAMEWORK.copy()
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',
]
