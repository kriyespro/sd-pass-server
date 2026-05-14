"""Serve extracted static student sites on project hostnames (e.g. kriss.apps.localhost)."""
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.static import serve

from apps.deployments.services import project_site_dir
from apps.projects.models import Project

# When folder upload uses only the image directory, browsers often send bare filenames
# (e.g. 6.jpg) while HTML still references img/6.jpg. Try these first-segment names only
# for two-part paths, and only if the nested path is missing.
_FLATTEN_IF_MISSING_TOP = frozenset(
    {'img', 'image', 'images', 'pics', 'photos', 'media', 'pictures', 'assets'},
)


def _host_without_port(raw: str) -> str:
    """
    Host part of HTTP Host header. Do not use split(':')[0] — it breaks
    ``radha.example.com:9898`` into ``radha`` instead of ``radha.example.com``.
    """
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw.startswith('['):
        end = raw.find(']')
        if end != -1 and len(raw) > end + 1 and raw[end + 1] == ':':
            return raw[: end + 1].lower()
        return raw.lower()
    if ':' in raw:
        host, maybe_port = raw.rsplit(':', 1)
        if maybe_port.isdigit():
            return host.lower()
    return raw.lower()


def _resolve_site_file_rel(root: Path, url_path: str) -> str | None:
    """
    Map request path to a path relative to site root for django.views.static.serve.
    Returns None if the URL must not be served (caller may 404/400).
    """
    if not url_path:
        return 'index.html'

    rel = Path(url_path)
    if '..' in rel.parts:
        return None

    primary = root / rel
    if primary.is_file():
        return rel.as_posix()
    if primary.is_dir():
        return (rel / 'index.html').as_posix()

    parts = rel.parts
    if len(parts) == 2 and parts[0].lower() in _FLATTEN_IF_MISSING_TOP:
        leaf = parts[1]
        if '..' in Path(leaf).parts:
            return None
        flat = root / leaf
        if flat.is_file():
            return Path(leaf).as_posix()

    return rel.as_posix()

_NO_INDEX_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Site bundle</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;}
code{background:#eee;padding:0 .25rem;}</style></head><body>
<h1>No <code>index.html</code> at ZIP root</h1>
<p>Your files were extracted, but the home URL (<code>/</code>) needs an <code>index.html</code>
in the <strong>top level</strong> of the ZIP (not only inside a subfolder).</p>
<p>Fix the ZIP, set the project type to <strong>Static</strong>, and upload again.</p>
</body></html>"""

_UNKNOWN_SUBDOMAIN = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Unknown app</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;}</style></head><body>
<h1>No project for this hostname</h1>
<p>There is no active project whose subdomain matches this host. Check the
<strong>Subdomain</strong> on your project dashboard — it must match the part before
<code>.{base}</code>.</p>
</body></html>"""

_DOMAIN_PENDING_VERIFY = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Domain not verified</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;}</style></head><body>
<h1>Domain not verified yet</h1>
<p>This hostname is linked to a project, but <strong>DNS verification</strong> is still pending.
Add the TXT record shown on your project’s <strong>Custom domain</strong> page, then use
<strong>Check verification</strong> or wait a few minutes.</p>
</body></html>"""


def _resolve_project_for_static_host(host: str):
    """
    Return a Project to serve, an HttpResponse to return immediately, or None
    to let Django handle the request (host is not a student site hostname).
    """
    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.').lower()
    suffix = f'.{base}'
    if host.endswith(suffix) and host != base:
        sub = host[: -len(suffix)]
        if not sub:
            return None
        project = (
            Project.objects.filter(subdomain__iexact=sub, is_deleted=False)
            .only('id', 'subdomain', 'slug', 'custom_hostname')
            .first()
        )
        if project is None:
            return HttpResponse(
                _UNKNOWN_SUBDOMAIN.format(base=base),
                status=404,
                content_type='text/html; charset=utf-8',
            )
        return project

    project = (
        Project.objects.filter(
            custom_hostname__iexact=host,
            is_deleted=False,
            custom_hostname_verified=True,
        )
        .only('id', 'subdomain', 'slug', 'custom_hostname')
        .first()
    )
    if project is not None:
        return project
    if (
        Project.objects.filter(
            custom_hostname__iexact=host,
            is_deleted=False,
            custom_hostname_verified=False,
        )
        .exclude(custom_hostname__isnull=True)
        .exclude(custom_hostname='')
        .exists()
    ):
        return HttpResponse(
            _DOMAIN_PENDING_VERIFY,
            status=503,
            content_type='text/html; charset=utf-8',
        )
    return None


class StudentStaticSiteMiddleware:
    """
    Serve static bundles for ``{subdomain}.{STUDENT_APPS_BASE_DOMAIN}`` or for an optional
    ``Project.custom_hostname``, from ``STUDENT_SITE_ROOT/<project_id>/``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self._maybe_static_site(request)
        if response is not None:
            return response
        return self.get_response(request)

    def _maybe_static_site(self, request):
        if request.method not in ('GET', 'HEAD'):
            return None

        host = _host_without_port(request.get_host())
        resolved = _resolve_project_for_static_host(host)
        if resolved is None:
            return None
        if isinstance(resolved, HttpResponse):
            return resolved
        project = resolved

        root = project_site_dir(project)
        if not root.is_dir():
            return HttpResponse(
                'No published site bundle yet. Upload a ZIP (Static project) from the dashboard.',
                status=503,
                content_type='text/plain; charset=utf-8',
            )
        if not any(root.iterdir()):
            return HttpResponse(
                'No published site bundle yet. Upload a ZIP (Static project) from the dashboard.',
                status=503,
                content_type='text/plain; charset=utf-8',
            )

        document_root = str(root)
        url_path = request.path.lstrip('/')
        if url_path and '..' in Path(url_path).parts:
            return HttpResponse('Invalid path.', status=400, content_type='text/plain; charset=utf-8')

        rel = _resolve_site_file_rel(root, url_path)
        if rel is None:
            return HttpResponse('Invalid path.', status=400, content_type='text/plain; charset=utf-8')

        try:
            root_resolved = root.resolve()
            target = (root / rel).resolve()
        except OSError:
            return HttpResponse(
                'Site directory is not readable.',
                status=503,
                content_type='text/plain; charset=utf-8',
            )

        if not target.is_relative_to(root_resolved):
            return HttpResponse('Invalid path.', status=400, content_type='text/plain; charset=utf-8')

        if not target.is_file():
            if not url_path and rel == 'index.html':
                return HttpResponse(_NO_INDEX_HTML, status=200, content_type='text/html; charset=utf-8')
            raise Http404()

        return serve(request, rel, document_root=document_root, show_indexes=False)
