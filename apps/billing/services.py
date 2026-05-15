"""Billing business logic — coupon redemption, plan limits."""
from __future__ import annotations

from django.utils import timezone

from .models import PLAN_LIMITS, CouponCode, Subscription


def user_project_limit(user) -> int:
    """Return how many projects this user is allowed to create."""
    try:
        sub = user.subscription
        return sub.max_projects
    except Subscription.DoesNotExist:
        pass
    return PLAN_LIMITS['free']


def get_or_create_subscription(user) -> Subscription:
    sub, _ = Subscription.objects.get_or_create(
        user=user,
        defaults={'plan_slug': Subscription.Plan.FREE, 'status': Subscription.Status.ACTIVE},
    )
    return sub


def redeem_coupon(user, code: str) -> tuple[bool, str]:
    """
    Redeem *code* for *user*.
    Returns (True, plan_slug) on success or (False, error_message) on failure.
    """
    code_clean = code.strip().upper().replace(' ', '')
    try:
        coupon = CouponCode.objects.select_for_update().get(code=code_clean)
    except CouponCode.DoesNotExist:
        return False, 'Invalid coupon code. Please check and try again.'

    if not coupon.is_redeemable:
        if coupon.used_by_id:
            return False, 'This coupon has already been used.'
        if coupon.expires_at and coupon.expires_at < timezone.now():
            return False, 'This coupon has expired.'
        return False, 'This coupon is no longer active.'

    now = timezone.now()
    period_end = now + timezone.timedelta(days=coupon.valid_days)

    sub = get_or_create_subscription(user)
    sub.plan_slug = coupon.plan
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = period_end
    sub.save()

    coupon.used_by = user
    coupon.redeemed_at = now
    coupon.is_active = False
    coupon.save()

    return True, coupon.plan
