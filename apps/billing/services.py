from apps.billing.models import Subscription


def get_or_create_subscription(user):
    sub, _ = Subscription.objects.get_or_create(
        user=user,
        defaults={
            'plan_slug': Subscription.Plan.FREE,
            'status': Subscription.Status.ACTIVE,
        },
    )
    return sub
