_NAV_CACHE_TTL = 30  # seconds — stale-ish but saves 2 DB queries per request


def google_auth(request):
    """Google OAuth button URL + flags on every page (login/register templates)."""
    from django.conf import settings
    from django.urls import NoReverseMatch, reverse

    google_login_url = ''
    try:
        google_login_url = reverse('google_login')
    except NoReverseMatch:
        pass
    return {
        'google_login_url': google_login_url,
        'google_oauth_configured': bool(getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')),
        'show_manual_auth': bool(getattr(settings, 'SHOW_MANUAL_AUTH', False)),
    }


def studentcloud_nav(request):
    """
    Jinja2 context: unread notifications + trainer menu visibility.
    Results are cached per-user for _NAV_CACHE_TTL seconds.
    """
    out = {
        'notification_unread_count': 0,
        'trainer_portal_visible': False,
    }
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return out

    from django.core.cache import cache

    from apps.dashboard.trainer_access import is_trainer
    from apps.notifications.models import Notification

    uid = request.user.pk
    cache_key = f'sdpaas:nav:{uid}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    out['notification_unread_count'] = Notification.objects.filter(
        user=request.user, read_at__isnull=True
    ).count()
    out['trainer_portal_visible'] = is_trainer(request.user)

    try:
        cache.set(cache_key, out, _NAV_CACHE_TTL)
    except Exception:
        pass

    return out
