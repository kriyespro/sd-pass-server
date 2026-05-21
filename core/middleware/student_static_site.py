"""Serve extracted static student sites on project hostnames (e.g. kriss.apps.localhost)."""
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.views.static import serve

from apps.deployments.services import project_site_dir
from apps.projects.models import Project

# When folder upload uses only the image directory, browsers often send bare filenames
# (e.g. 6.jpg) while HTML still references img/6.jpg. Try these first-segment names only
# for two-part paths, and only if the nested path is missing.
_FLATTEN_IF_MISSING_TOP = frozenset(
    {'img', 'image', 'images', 'pics', 'photos', 'media', 'pictures', 'assets'},
)

# Cache project PK by host to avoid 2 DB queries per static site request.
# TTL=30s: new deploy appears to visitors within 30 seconds.
_PROJ_HOST_CACHE_PREFIX = 'studentsite:host:'
_TRIAL_CACHE_PREFIX = 'studentsite:trial:'
_FREE_PLAN_CACHE_PREFIX = 'studentsite:free_plan:'
_SUBFOLDER_LIST_CACHE_PREFIX = 'studentsite:subfolders:'
_SITE_CACHE_TTL = 30


def invalidate_site_host_cache(project) -> None:
    """Call after deploy or delete so the next request re-fetches the project."""
    base = getattr(settings, 'STUDENT_APPS_BASE_DOMAIN', '').strip().strip('.').lower()
    sub_host = f'{(project.subdomain or "").lower()}.{base}'
    cache.delete(_PROJ_HOST_CACHE_PREFIX + sub_host)
    if project.custom_hostname:
        cache.delete(_PROJ_HOST_CACHE_PREFIX + project.custom_hostname.strip().lower())
    cache.delete(_TRIAL_CACHE_PREFIX + str(project.owner_id))
    cache.delete(_FREE_PLAN_CACHE_PREFIX + str(project.owner_id))
    cache.delete(_SUBFOLDER_LIST_CACHE_PREFIX + str(project.pk))


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

_SUBFOLDER_BLOCKED = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Paid plan required</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:36rem;margin:4rem auto;padding:0 1.5rem;background:#0f172a;color:#e2e8f0;}}
h1{{color:#f8fafc;font-size:1.5rem;margin-bottom:.75rem;}}
p{{color:#94a3b8;line-height:1.6;margin:.5rem 0;}}
a.btn{{display:inline-block;margin-top:1.25rem;padding:.6rem 1.4rem;background:#6366f1;color:#fff;border-radius:.5rem;text-decoration:none;font-weight:600;}}
a.btn:hover{{background:#4f46e5;}}
</style></head><body>
<h1>Subfolder sites require a paid plan</h1>
<p>This site is deployed inside a subfolder path which is only available on paid plans.</p>
<p>Upgrade your account to restore access, or re-deploy to the site root.</p>
<a class="btn" href="{upgrade_url}">Upgrade account</a>
</body></html>"""

_TRIAL_EXPIRED = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Free trial ended</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:36rem;margin:4rem auto;padding:0 1.5rem;background:#0f172a;color:#e2e8f0;}}
h1{{color:#f8fafc;font-size:1.5rem;margin-bottom:.75rem;}}
p{{color:#94a3b8;line-height:1.6;margin:.5rem 0;}}
a.btn{{display:inline-block;margin-top:1.25rem;padding:.6rem 1.4rem;background:#6366f1;color:#fff;border-radius:.5rem;text-decoration:none;font-weight:600;}}
a.btn:hover{{background:#4f46e5;}}
</style></head><body>
<h1>Your free trial has ended</h1>
<p>This website is on a free trial plan that has expired.</p>
<p>Upgrade your account to restore public access to this site.</p>
<a class="btn" href="{upgrade_url}">Upgrade account</a>
</body></html>"""


def _resolve_project_for_static_host(host: str):
    """
    Return a Project to serve, an HttpResponse to return immediately, or None
    to let Django handle the request (host is not a student site hostname).

    Results are cached for _SITE_CACHE_TTL seconds to avoid a DB hit on every
    static site request. Call invalidate_site_host_cache() on deploy / delete.
    """
    cache_key = _PROJ_HOST_CACHE_PREFIX + host
    cached_pk = cache.get(cache_key)
    if cached_pk is not None:
        project = (
            Project.objects.filter(pk=cached_pk, is_deleted=False)
            .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'custom_hostname_verified')
            .first()
        )
        if project:
            # Re-check custom domain verification on cache hit (status can change)
            if project.custom_hostname and not project.custom_hostname_verified:
                return HttpResponse(_DOMAIN_PENDING_VERIFY, status=503, content_type='text/html; charset=utf-8')
            return project
        # Project deleted after cache was set — invalidate and fall through
        cache.delete(cache_key)

    base = settings.STUDENT_APPS_BASE_DOMAIN.strip().strip('.').lower()
    suffix = f'.{base}'
    if host.endswith(suffix) and host != base:
        sub = host[: -len(suffix)]
        if not sub:
            return None
        project = (
            Project.objects.filter(subdomain__iexact=sub, is_deleted=False)
            .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname')
            .first()
        )
        if project is None:
            return HttpResponse(
                _UNKNOWN_SUBDOMAIN.format(base=base),
                status=404,
                content_type='text/html; charset=utf-8',
            )
        cache.set(cache_key, project.pk, _SITE_CACHE_TTL)
        return project

    project = (
        Project.objects.filter(
            custom_hostname__iexact=host,
            is_deleted=False,
        )
        .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'custom_hostname_verified')
        .first()
    )
    if project is None:
        return None
    if project.custom_hostname_verified:
        cache.set(cache_key, project.pk, _SITE_CACHE_TTL)
        return project
    return HttpResponse(
        _DOMAIN_PENDING_VERIFY,
        status=503,
        content_type='text/html; charset=utf-8',
    )


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

    @staticmethod
    def _is_free_plan(project) -> bool:
        cache_key = _FREE_PLAN_CACHE_PREFIX + str(project.owner_id)
        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)
        try:
            from apps.billing.models import Subscription
            sub = Subscription.objects.only(
                'plan_slug', 'status', 'trial_ends_at', 'current_period_end'
            ).get(user_id=project.owner_id)
            result = not sub.is_paid
        except Exception:
            result = False
        cache.set(cache_key, result, _SITE_CACHE_TTL)
        return result

    @staticmethod
    def _project_subfolder_paths(project_id: int) -> frozenset:
        cache_key = _SUBFOLDER_LIST_CACHE_PREFIX + str(project_id)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            from apps.projects.models import ProjectSubfolder
            paths = frozenset(
                ProjectSubfolder.objects
                .filter(project_id=project_id)
                .exclude(path='')
                .values_list('path', flat=True)
            )
        except Exception:
            paths = frozenset()
        cache.set(cache_key, paths, _SITE_CACHE_TTL)
        return paths

    @staticmethod
    def _is_trial_expired(project) -> bool:
        cache_key = _TRIAL_CACHE_PREFIX + str(project.owner_id)
        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)
        try:
            from apps.billing.models import Subscription
            sub = Subscription.objects.only('plan_slug', 'trial_ends_at').get(user_id=project.owner_id)
            result = sub.trial_expired
        except Exception:
            result = False
        cache.set(cache_key, result, _SITE_CACHE_TTL)
        return result

    @staticmethod
    def _upgrade_url(request) -> str:
        try:
            from django.urls import reverse
            path = reverse('billing:redeem')
            # Must use the main platform domain, not the student site host.
            # request.build_absolute_uri() would produce e.g. https://kriss.crorepatinetwork.com/billing/redeem/
            # which the middleware intercepts → 404.
            origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
            if origins:
                base = origins[0].rstrip('/')
            else:
                allowed = getattr(settings, 'ALLOWED_HOSTS', [])
                host = next((h for h in allowed if not h.startswith('.')), 'localhost')
                scheme = 'https' if not host.startswith('localhost') else 'http'
                base = f'{scheme}://{host}'
            return base + path
        except Exception:
            return '/billing/redeem/'

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

        if self._is_trial_expired(project):
            upgrade_url = self._upgrade_url(request)
            return HttpResponse(
                _TRIAL_EXPIRED.format(upgrade_url=upgrade_url),
                status=402,
                content_type='text/html; charset=utf-8',
            )

        if self._is_free_plan(project):
            url_path = request.path.lstrip('/')
            if url_path:
                subfolder_paths = self._project_subfolder_paths(project.pk)
                for sf in subfolder_paths:
                    if url_path == sf or url_path.startswith(sf + '/'):
                        upgrade_url = self._upgrade_url(request)
                        return HttpResponse(
                            _SUBFOLDER_BLOCKED.format(upgrade_url=upgrade_url),
                            status=402,
                            content_type='text/html; charset=utf-8',
                        )

        root = project_site_dir(project)
        try:
            has_contents = any(root.iterdir())
        except OSError:
            has_contents = False
        if not has_contents:
            return HttpResponse(
                'No published site bundle yet. Upload a ZIP (Static project) from the dashboard.',
                status=503,
                content_type='text/plain; charset=utf-8',
            )

        document_root = str(root)
        url_path = request.path.lstrip('/')
        if url_path and '..' in Path(url_path).parts:
            return HttpResponse('Invalid path.', status=400, content_type='text/plain; charset=utf-8')

        # Redirect /folder → /folder/ so relative URLs in HTML resolve correctly.
        # Without this, <link href="style.css"> at /folder resolves to /style.css (wrong).
        if url_path and not request.path.endswith('/') and (root / Path(url_path)).is_dir():
            redirect_to = request.path + '/'
            qs = request.META.get('QUERY_STRING', '')
            if qs:
                redirect_to += '?' + qs
            return HttpResponsePermanentRedirect(redirect_to)

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

        response = serve(request, rel, document_root=document_root, show_indexes=False)
        # Force browsers to revalidate every request via ETag/Last-Modified.
        # Without this, browsers use heuristic caching and images won't refresh after re-upload.
        response['Cache-Control'] = 'no-cache'
        return response
