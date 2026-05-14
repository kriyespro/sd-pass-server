from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from jinja2 import Environment


def reverse_url(viewname, *args, **kwargs):
    if kwargs:
        return reverse(viewname, kwargs=kwargs)
    if args:
        return reverse(viewname, args=args)
    return reverse(viewname)


def environment(**options):
    env = Environment(**options)
    env.globals.update(
        static=staticfiles_storage.url,
        url=reverse_url,
    )
    return env
