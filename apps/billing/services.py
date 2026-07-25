"""Billing business logic — coupon redemption, plan limits."""
from __future__ import annotations

from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

from .models import (
    FLASK_LIMITS,
    FREE_TRIAL_DAYS,
    NEW_USER_TRIAL_DAYS,
    PLAN_LIMITS,
    CouponCode,
    PlanAddon,
    Subscription,
    plan_docker_limits,
)

# Container-hosted project types (php.txt Phase 2-4). Plain strings, not
# apps.projects.models.ProjectType members — apps.projects already imports this
# module (user_flask_limit etc.), so importing ProjectType here would be circular.
CONTAINER_HOSTED_PROJECT_TYPES = frozenset({'wordpress', 'php', 'drupal'})

# wordpress_pro and up — see php.txt section 10, decision 4.
CONTAINER_HOSTING_PLANS = frozenset({'wordpress_pro', 'business_cloud', 'agency_turbo', 'performance_max'})


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

    base = PLAN_LIMITS['free']
    try:
        sub = user.subscription
        base = sub.max_projects
    except Subscription.DoesNotExist:
        pass

    # Sum extra slots from active add-on purchases.
    addon_extra = sum(
        a.extra_projects
        for a in PlanAddon.objects.filter(
            user=user,
            status=PlanAddon.Status.ACTIVE,
            current_period_end__gt=timezone.now(),
        )
    )
    return base + addon_extra


def user_flask_limit(user) -> int:
    """Return how many Flask app projects this user is allowed."""
    try:
        override = user.quota_config.max_projects
        if override is not None:
            return override
    except Exception:
        pass

    base = 0
    try:
        sub = user.subscription
        base = sub.max_flask_projects
    except Subscription.DoesNotExist:
        pass

    addon_extra = sum(
        a.extra_flask_projects
        for a in PlanAddon.objects.filter(
            user=user,
            status=PlanAddon.Status.ACTIVE,
            current_period_end__gt=timezone.now(),
        )
    )
    return base + addon_extra


def user_can_create_project_type(user, project_type: str) -> bool:
    """
    WordPress/PHP/Drupal projects are container-hosted (php.txt Phase 2-4) and cost
    real host resources per project — gated behind wordpress_pro and up. Static and
    Flask are unaffected (Flask has its own gate via user_flask_limit). Called from
    apps.projects.forms.ProjectForm (WP-4/PHP-6/DRU-5).
    """
    if project_type not in CONTAINER_HOSTED_PROJECT_TYPES:
        return True
    try:
        return user.subscription.plan_slug in CONTAINER_HOSTING_PLANS
    except Exception:
        return False


def docker_limits_for_project(project) -> dict:
    """
    Return {'app': {'mem_limit', 'nano_cpus'}, 'mysql': {...}} for a container-hosted
    project's docker run, derived from the owning user's plan
    (models.py::plan_docker_limits / PLAN_HOSTING_SPECS). See php.txt INF-6.
    """
    plan_slug = Subscription.Plan.FREE
    try:
        plan_slug = project.owner.subscription.plan_slug
    except Exception:
        pass
    return plan_docker_limits(plan_slug)


def sync_container_projects_for_subscription(user) -> None:
    """
    Suspend or restore docker containers for this user's WordPress/PHP/Drupal
    projects to match their current subscription status (php.txt Phase 5, BIL-1).
    Call this anywhere Subscription.status transitions between ACTIVE and SUSPENDED.
    A no-op for users with no container-hosted projects.
    """
    from apps.containers.services import suspend_project_containers, unsuspend_project_containers
    from apps.projects.models import Project

    try:
        sub = user.subscription
    except Exception:
        return

    if sub.status not in (Subscription.Status.ACTIVE, Subscription.Status.SUSPENDED):
        return

    projects = Project.objects.filter(
        owner=user, is_deleted=False, project_type__in=CONTAINER_HOSTED_PROJECT_TYPES,
    )
    if sub.status == Subscription.Status.SUSPENDED:
        for project in projects:
            suspend_project_containers(project)
    else:
        for project in projects:
            unsuspend_project_containers(project)


def get_or_create_subscription(user) -> Subscription:
    from django.utils import timezone
    now = timezone.now()
    trial_end = now + timezone.timedelta(days=NEW_USER_TRIAL_DAYS)
    sub, created = Subscription.objects.get_or_create(
        user=user,
        defaults={
            'plan_slug': Subscription.Plan.FREE,
            'status': Subscription.Status.ACTIVE,
            'current_period_end': trial_end,
            'trial_ends_at': trial_end,
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
        sub.trial_ends_at = None
        sub.save()

        coupon.used_by = user
        coupon.redeemed_at = now
        coupon.is_active = False
        coupon.save()

    sync_container_projects_for_subscription(user)
    return True, coupon.plan
