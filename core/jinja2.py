import json

from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from jinja2 import Environment
from markupsafe import Markup


def reverse_url(viewname, *args, **kwargs):
    if kwargs:
        return reverse(viewname, kwargs=kwargs)
    if args:
        return reverse(viewname, args=args)
    return reverse(viewname)


def _tojson(value):
    """JSON serialization safe for inline <script> tags (escapes </script> breakout)."""
    return Markup(
        json.dumps(value, ensure_ascii=False)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )


def environment(**options):
    env = Environment(**options)
    env.globals.update(
        static=staticfiles_storage.url,
        url=reverse_url,
    )
    env.filters['tojson'] = _tojson
    return env
