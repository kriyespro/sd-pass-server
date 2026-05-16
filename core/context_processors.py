_NAV_CACHE_TTL = 30  # seconds — stale-ish but saves 2 DB queries per request


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
