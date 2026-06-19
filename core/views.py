from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

_ROBOTS_ALLOW = [
    '/',
    '/hosting/',
    '/server/',
    '/pricing/',
    '/features/',
    '/resell/',
    '/accounts/register/',
]

_ROBOTS_DISALLOW = [
    '/projects/',
    '/billing/',
    '/notifications/',
    '/onboarding/',
    '/admin/',
    '/ops/',
    '/trainer/',
    '/api/',
    '/sd/',
    '/accounts/logout/',
    '/accounts/manual/',
]


def home(request):
    response = render(request, 'pages/home.jinja', {})
    if not request.user.is_authenticated:
        response['Cache-Control'] = 'public, max-age=300, stale-while-revalidate=60'
    return response


def robots_txt(request):
    domain = getattr(settings, 'SITE_DOMAIN', request.get_host())
    lines = ['User-agent: *']
    for path in _ROBOTS_ALLOW:
        lines.append(f'Allow: {path}')
    for path in _ROBOTS_DISALLOW:
        lines.append(f'Disallow: {path}')
    lines.append('')
    lines.append(f'Sitemap: https://{domain}/sitemap.xml')
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def handler404(request, exception):
    return render(request, 'pages/errors/404.jinja', status=404)


def handler500(request):
    return render(request, 'pages/errors/500.jinja', status=500)
