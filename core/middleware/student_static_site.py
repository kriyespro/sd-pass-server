"""Serve extracted static student sites on project hostnames (e.g. kriss.apps.localhost)."""
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.views.static import serve

from apps.deployments.services import project_site_dir
from apps.projects.models import Project

# Common image/asset folder names students use. When a request for one of these
# folders fails, we try every other alias and also the flat-at-root fallback.
# E.g. HTML uses /img/photo.jpg but files are in images/ → served transparently.
_IMAGE_FOLDER_ALIASES = frozenset(
    {'img', 'image', 'images', 'pics', 'photos', 'media', 'pictures', 'assets'},
)

# Keep old name as alias so nothing else in this file needs to change.
_FLATTEN_IF_MISSING_TOP = _IMAGE_FOLDER_ALIASES

# Cache project PK by host to avoid 2 DB queries per static site request.
# TTL=30s: new deploy appears to visitors within 30 seconds.
_PROJ_HOST_CACHE_PREFIX = 'studentsite:host:'
_TRIAL_CACHE_PREFIX = 'studentsite:trial:'
_FREE_PLAN_CACHE_PREFIX = 'studentsite:free_plan:'
_SUBFOLDER_LIST_CACHE_PREFIX = 'studentsite:subfolders:'
_HAS_FILES_CACHE_PREFIX = 'studentsite:hasfiles:'
_SITE_CACHE_TTL = 30


def invalidate_site_host_cache(project) -> None:
    """Call after deploy or delete so the next request re-fetches the project."""
    from apps.projects.host_allowlist import hostname_aliases

    base = getattr(settings, 'STUDENT_APPS_BASE_DOMAIN', '').strip().strip('.').lower()
    sub_host = f'{(project.subdomain or "").lower()}.{base}'
    cache.delete(_PROJ_HOST_CACHE_PREFIX + sub_host)
    if project.custom_hostname:
        for alias in hostname_aliases(project.custom_hostname):
            cache.delete(_PROJ_HOST_CACHE_PREFIX + alias)
    cache.delete(_TRIAL_CACHE_PREFIX + str(project.owner_id))
    cache.delete(_FREE_PLAN_CACHE_PREFIX + str(project.owner_id))
    cache.delete(_SUBFOLDER_LIST_CACHE_PREFIX + str(project.pk))
    cache.delete(_HAS_FILES_CACHE_PREFIX + str(project.pk))


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

    Alias resolution when the exact path is missing:

    Case A — no subfolder prefix, image alias is first segment:
      images/photo.jpg  →  try img/, image/, photos/, … + flat at root

    Case B — one subfolder prefix, image alias is second segment:
      portfolio/images/photo.jpg  →  try portfolio/img/, … + flat in portfolio/

    Both cases handle any nesting depth beyond the alias (e.g. images/gallery/photo.jpg).
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

    # Files are stored lowercase (upload normalisation lowercases every path segment).
    # HTML may still reference original mixed-case names (e.g. Hero.JPG → hero.jpg).
    # Try lowercasing the full path before alias resolution.
    lower_rel = Path(*[p.lower() for p in rel.parts]) if rel.parts else rel
    if lower_rel != rel:
        lower_candidate = root / lower_rel
        if lower_candidate.is_file():
            return lower_rel.as_posix()
        if lower_candidate.is_dir():
            return (lower_rel / 'index.html').as_posix()

    parts = rel.parts

    # Case A: first segment is a known image-folder alias (no subfolder prefix).
    # e.g. images/photo.jpg, img/gallery/photo.jpg
    if len(parts) >= 2 and parts[0].lower() in _IMAGE_FOLDER_ALIASES:
        tail = parts[1:]
        tail_lower = tuple(p.lower() for p in tail)
        for alias in _IMAGE_FOLDER_ALIASES:
            if alias == parts[0].lower():
                continue
            candidate = Path(alias, *tail)
            if (root / candidate).is_file():
                return candidate.as_posix()
            # Also try lowercase tail (uploaded files are normalised to lowercase).
            if tail_lower != tail:
                candidate_lower = Path(alias, *tail_lower)
                if (root / candidate_lower).is_file():
                    return candidate_lower.as_posix()
        # Flat fallback: try file at site root (no folder), original then lowercase.
        if len(parts) == 2 and '..' not in Path(parts[1]).parts:
            flat = root / parts[1]
            if flat.is_file():
                return Path(parts[1]).as_posix()
            flat_lower = root / parts[1].lower()
            if flat_lower.is_file():
                return Path(parts[1].lower()).as_posix()

    # Case B: second segment is a known image-folder alias (one subfolder prefix).
    # e.g. portfolio/images/photo.jpg when file is at portfolio/img/photo.jpg
    #      or portfolio/images/photo.jpg when file is flat at portfolio/photo.jpg
    elif len(parts) >= 3 and parts[1].lower() in _IMAGE_FOLDER_ALIASES:
        subfolder = parts[0]
        tail = parts[2:]
        tail_lower = tuple(p.lower() for p in tail)
        for alias in _IMAGE_FOLDER_ALIASES:
            if alias == parts[1].lower():
                continue
            candidate = Path(subfolder, alias, *tail)
            if (root / candidate).is_file():
                return candidate.as_posix()
            if tail_lower != tail:
                candidate_lower = Path(subfolder, alias, *tail_lower)
                if (root / candidate_lower).is_file():
                    return candidate_lower.as_posix()
        # Flat fallback: try file directly inside the subfolder, original then lowercase.
        if len(parts) == 3 and '..' not in Path(parts[2]).parts:
            flat = root / subfolder / parts[2]
            if flat.is_file():
                return (Path(subfolder) / parts[2]).as_posix()
            flat_lower = root / subfolder / parts[2].lower()
            if flat_lower.is_file():
                return (Path(subfolder) / parts[2].lower()).as_posix()

    # Extension fallback: URL has no .html/.htm but the file exists with one.
    # Handles links like href="/about" when only about.html is on disk.
    # Try original case then lowercase (uploaded files are normalised to lowercase).
    if rel.suffix.lower() not in ('.html', '.htm'):
        url_path_lower = url_path.lower()
        for ext in ('.html', '.htm'):
            candidate = root / (url_path + ext)
            if candidate.is_file():
                return (rel.as_posix() + ext)
            if url_path_lower != url_path:
                candidate_lower = root / (url_path_lower + ext)
                if candidate_lower.is_file():
                    return (url_path_lower + ext)

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
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Plan Expired — Krizn</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
      min-height:100vh;
      background:radial-gradient(ellipse at 60% 0%,#0d2d1f 0%,#0f172a 55%,#0f0f1a 100%);
      color:#e2e8f0;
      display:flex;align-items:center;justify-content:center;
      padding:2rem 1.25rem;
    }}
    .card{{
      width:100%;max-width:34rem;
      background:rgba(15,23,42,.85);
      border:1px solid rgba(16,185,129,.18);
      border-radius:1.5rem;
      padding:2.5rem 2rem;
      box-shadow:0 0 60px rgba(16,185,129,.07),0 24px 48px rgba(0,0,0,.5);
      text-align:center;
    }}
    .fuel-icon{{font-size:3rem;line-height:1;margin-bottom:1.25rem;display:block}}
    .eyebrow{{
      display:inline-block;margin-bottom:1rem;
      background:rgba(16,185,129,.12);
      border:1px solid rgba(16,185,129,.3);
      border-radius:999px;
      padding:.3rem .9rem;
      font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
      color:#34d399;
    }}
    h1{{
      font-size:1.45rem;font-weight:800;line-height:1.3;
      color:#f8fafc;margin-bottom:1rem;
    }}
    .msg{{
      font-size:.9rem;line-height:1.7;color:#94a3b8;
      margin-bottom:.6rem;
    }}
    .msg strong{{color:#cbd5e1}}
    .divider{{
      height:1px;background:rgba(255,255,255,.06);
      margin:1.5rem 0;
    }}
    .price-pill{{
      display:inline-flex;align-items:baseline;gap:.35rem;
      background:rgba(16,185,129,.1);
      border:1px solid rgba(16,185,129,.25);
      border-radius:.75rem;
      padding:.5rem 1.1rem;
      margin-bottom:1.5rem;
    }}
    .price-pill .amount{{font-size:1.6rem;font-weight:900;color:#ecfdf5}}
    .price-pill .period{{font-size:.8rem;color:#6ee7b7}}
    .btn{{
      display:inline-flex;align-items:center;gap:.5rem;
      background:linear-gradient(135deg,#10b981,#059669);
      color:#022c22;
      font-weight:800;font-size:.9rem;
      padding:.75rem 1.75rem;
      border-radius:.75rem;
      text-decoration:none;
      box-shadow:0 4px 20px rgba(16,185,129,.3);
      transition:transform .15s,box-shadow .15s;
    }}
    .btn:hover{{transform:translateY(-2px);box-shadow:0 8px 28px rgba(16,185,129,.4)}}
    .btn:active{{transform:translateY(0)}}
    .footer{{margin-top:1.5rem;font-size:.72rem;color:#475569}}
    .dot{{
      display:inline-block;width:.4rem;height:.4rem;border-radius:50%;
      background:#10b981;vertical-align:middle;margin-right:.4rem;
      animation:ping 1.5s ease-in-out infinite;
    }}
    @keyframes ping{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.4;transform:scale(1.4)}}}}
  </style>
</head>
<body>
  <div class="card">
    <span class="fuel-icon">⛽</span>
    <span class="eyebrow"><span class="dot"></span>Plan Expired</span>
    <h1>We need a little fuel<br>to keep going ❤️</h1>
    <p class="msg">
      Dear visitor, running fast cloud servers costs real money —
      <strong>and our fuel bill just went up!</strong>
    </p>
    <p class="msg">
      To keep this site online and Krizn blazing fast for everyone,
      the owner needs to activate a paid plan.
      Plans start at ₹299 for 30 days of full access.
    </p>
    <p class="msg">Thanks for your patience and support — it truly means a lot to us. 🙏</p>
    <div class="divider"></div>
    <div class="price-pill">
      <span class="amount">₹299</span>
      <span class="period">/ 30 days · full access</span>
    </div>
    <br>
    <a class="btn" href="{upgrade_url}">
      🚀 Login &amp; Restore this site — ₹299
    </a>
    <p class="footer" style="margin-top:.75rem;color:#64748b;font-size:.72rem;">
      Are you the site owner? Log in to your Krizn account and activate a plan to bring this site back online.
    </p>
    <p class="footer">Krizn · Affordable Cloud Hosting for Students</p>
  </div>
</body>
</html>"""


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
            .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'custom_hostname_verified', 'site_subfolder', 'project_type', 'flask_port')
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
            .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'site_subfolder', 'project_type', 'flask_port')
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
        .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'custom_hostname_verified', 'site_subfolder', 'project_type', 'flask_port')
        .first()
    )
    if project is None:
        # www.example.com ↔ example.com — same site when only one form was saved.
        from apps.projects.host_allowlist import sibling_hostname
        sib = sibling_hostname(host)
        if sib:
            project = (
                Project.objects.filter(
                    custom_hostname__iexact=sib,
                    is_deleted=False,
                )
                .only('id', 'owner_id', 'subdomain', 'slug', 'custom_hostname', 'custom_hostname_verified', 'site_subfolder', 'project_type', 'flask_port')
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
        """Return True when the site owner's account is suspended or their paid trial has expired."""
        cache_key = _TRIAL_CACHE_PREFIX + str(project.owner_id)
        cached = cache.get(cache_key)
        if cached is not None:
            return bool(cached)
        try:
            from django.utils import timezone as tz
            from apps.billing.models import Subscription
            sub = Subscription.objects.only(
                'plan_slug', 'status', 'trial_ends_at', 'current_period_end'
            ).get(user_id=project.owner_id)
            # Explicitly suspended
            if sub.status == Subscription.Status.SUSPENDED:
                result = True
            # Legacy free trial expired
            elif sub.trial_expired:
                result = True
            # Paid trial (test_plan / any plan) whose period ended
            elif sub.current_period_end and sub.current_period_end < tz.now() and sub.plan_slug != Subscription.Plan.FREE:
                result = True
            else:
                result = False
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

    @staticmethod
    def _proxy_to_flask(request, flask_port):
        """Proxy an HTTP request to the Flask runner gunicorn process on flask_port."""
        import urllib.error
        import urllib.request as ureq

        _HOP = frozenset({
            'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
            'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
        })

        # Never follow redirects — return them to the browser so it handles
        # cookies and method correctly (POST → 302 → browser follows as GET).
        class _NoRedirect(ureq.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                raise ureq.HTTPError(req.full_url, code, msg, headers, fp)
            http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

        opener = ureq.build_opener(_NoRedirect())

        if not (7000 <= int(flask_port) <= 7999):
            return HttpResponse('Invalid app port.', status=502, content_type='text/plain')
        flask_runner_base = getattr(settings, 'FLASK_RUNNER_URL', 'http://flask-runner:6000')
        flask_host = flask_runner_base.rsplit(':', 1)[0]  # strip :6000 management port
        target = f'{flask_host}:{flask_port}{request.path}'
        if request.META.get('QUERY_STRING'):
            target += '?' + request.META['QUERY_STRING']

        headers = {}
        for key, val in request.META.items():
            if key.startswith('HTTP_'):
                name = key[5:].replace('_', '-').lower()
                if name not in _HOP:
                    headers[name] = val
            elif key == 'CONTENT_TYPE' and val:
                headers['content-type'] = val
            elif key == 'CONTENT_LENGTH' and val:
                headers['content-length'] = val
        headers['x-forwarded-proto'] = 'https'
        headers['x-forwarded-host'] = request.get_host()

        body = None
        if request.method in ('POST', 'PUT', 'PATCH'):
            try:
                body = request.body
            except Exception:
                body = None

        req = ureq.Request(target, data=body, headers=headers, method=request.method)
        try:
            with opener.open(req, timeout=30) as resp:
                content = resp.read()
                out = HttpResponse(content, status=resp.status)
                for name, val in resp.headers.items():
                    if name.lower() not in _HOP:
                        out[name] = val
                return out
        except ureq.HTTPError as exc:
            content = exc.read()
            out = HttpResponse(content, status=exc.code)
            for name, val in exc.headers.items():
                if name.lower() not in _HOP:
                    out[name] = val
            return out
        except (ureq.URLError, OSError):
            return HttpResponse(
                'Flask app is starting up or unavailable. Try again in a moment.',
                status=503, content_type='text/plain; charset=utf-8',
            )

    def _maybe_static_site(self, request):
        host = _host_without_port(request.get_host())
        resolved = _resolve_project_for_static_host(host)
        if resolved is None:
            return None
        if isinstance(resolved, HttpResponse):
            return resolved
        project = resolved

        # Canonicalize www ↔ apex to the hostname saved on the project (301).
        canonical = (project.custom_hostname or '').strip().lower().rstrip('.')
        if canonical and host.lower() != canonical:
            from apps.projects.host_allowlist import sibling_hostname
            if sibling_hostname(canonical) == host.lower():
                path = request.get_full_path() or '/'
                scheme = getattr(settings, 'STUDENT_SITE_PUBLIC_SCHEME', None) or (
                    'https' if request.is_secure() else 'http'
                )
                return HttpResponsePermanentRedirect(f'{scheme}://{canonical}{path}')

        # Flask projects: proxy all methods to the gunicorn process.
        # Custom domain traffic arrives here via nginx's default server block
        # (Traefik handles the *.krizn.com subdomain path directly).
        from apps.projects.models import ProjectType
        if project.project_type == ProjectType.FLASK:
            if not project.flask_port:
                return HttpResponse(
                    'Flask app not yet deployed. Upload a ZIP from the dashboard.',
                    status=503, content_type='text/plain; charset=utf-8',
                )
            return self._proxy_to_flask(request, project.flask_port)

        # Static projects — only serve GET and HEAD.
        if request.method not in ('GET', 'HEAD'):
            return None

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
        has_files_key = _HAS_FILES_CACHE_PREFIX + str(project.pk)
        has_contents = cache.get(has_files_key)
        if has_contents is None:
            try:
                has_contents = any(root.iterdir())
            except OSError:
                has_contents = False
            cache.set(has_files_key, has_contents, _SITE_CACHE_TTL)
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
            # Subfolder fallback: when a site was deployed into a subfolder (e.g.
            # 'test-html-website'), absolute-path references in its HTML like /styles.css
            # won't find files at the site root. Prepend project.site_subfolder and retry.
            sf = (getattr(project, 'site_subfolder', '') or '').strip().strip('/')
            if sf and not url_path.startswith(sf + '/'):
                sf_lookup = sf + '/' + url_path if url_path else sf
                sf_rel = _resolve_site_file_rel(root, sf_lookup)
                if sf_rel:
                    sf_target = (root / sf_rel).resolve()
                    if sf_target.is_relative_to(root_resolved) and sf_target.is_file():
                        rel = sf_rel
                        target = sf_target
        if not target.is_file():
            if not url_path and rel == 'index.html':
                return HttpResponse(_NO_INDEX_HTML, status=200, content_type='text/html; charset=utf-8')
            raise Http404()

        response = serve(request, rel, document_root=document_root, show_indexes=False)
        # Force browsers to revalidate every request via ETag/Last-Modified.
        # Without this, browsers use heuristic caching and images won't refresh after re-upload.
        response['Cache-Control'] = 'no-cache'
        return response
