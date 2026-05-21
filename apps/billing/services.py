"""Billing business logic — coupon redemption, plan limits."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

from .models import FREE_TRIAL_DAYS, PLAN_LIMITS, CouponCode, Subscription


def user_can_use_subfolder(user) -> bool:
    """Only paid (non-free) active subscribers may deploy to a path subfolder."""
    try:
        return user.subscription.is_paid
    except Exception:
        return False


def user_project_limit(user) -> int:
    """Return how many projects this user is allowed to create."""
    # Trainer-set override (explicit non-None value) takes priority over billing plan.
    try:
        override = user.quota_config.max_projects
        if override is not None:
            return override
    except Exception:
        pass
    try:
        sub = user.subscription
        return sub.max_projects
    except Subscription.DoesNotExist:
        pass
    return PLAN_LIMITS['free']


def get_or_create_subscription(user) -> Subscription:
    sub, created = Subscription.objects.get_or_create(
        user=user,
        defaults={
            'plan_slug': Subscription.Plan.FREE,
            'status': Subscription.Status.ACTIVE,
            'trial_ends_at': timezone.now() + timezone.timedelta(days=FREE_TRIAL_DAYS),
        },
    )
    return sub


def redeem_coupon(user, code: str) -> tuple[bool, str]:
    """
    Redeem *code* for *user*.
    Returns (True, plan_slug) on success or (False, error_message) on failure.

    Normalises both sides before comparing so STUD-ABCD-1234-EFGH, STUDABCD1234EFGH,
    and stud abcd 1234 efgh all resolve to the same stored coupon.
    """
    code_clean = code.strip().upper().replace(' ', '').replace('-', '')
    if not code_clean:
        return False, 'Please enter a coupon code.'

    with transaction.atomic():
        # Annotate DB codes with hyphens/spaces stripped so the lookup is symmetric.
        # This means STUD-ABCD-1234-EFGH matches STUDABCD1234EFGH typed by the user.
        coupon = (
            CouponCode.objects
            .annotate(
                code_norm=Upper(
                    Replace(
                        Replace('code', Value('-'), Value('')),
                        Value(' '), Value(''),
                    )
                )
            )
            .select_for_update()
            .filter(code_norm=code_clean)
            .first()
        )
        if coupon is None:
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
