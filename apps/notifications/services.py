from apps.notifications.models import Notification, NotificationLevel


def create_notification(
    *,
    user_id: int,
    title: str,
    body: str = '',
    level: str = NotificationLevel.INFO,
    link_url: str = '',
) -> Notification | None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if not User.objects.filter(pk=user_id).exists():
        return None
    return Notification.objects.create(
        user_id=user_id,
        title=title,
        body=body,
        level=level,
        link_url=link_url or '',
    )
