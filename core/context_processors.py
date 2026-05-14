def studentcloud_nav(request):
    """
    Jinja2 context: unread notifications + trainer menu visibility.
    """
    out = {
        'notification_unread_count': 0,
        'trainer_portal_visible': False,
    }
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return out
    from apps.dashboard.trainer_access import is_trainer
    from apps.notifications.models import Notification

    out['notification_unread_count'] = Notification.objects.filter(
        user=request.user, read_at__isnull=True
    ).count()
    out['trainer_portal_visible'] = is_trainer(request.user)
    return out
