from django.utils import timezone

from apps.accounts.services import profile_is_complete
from apps.projects.models import Project

from .models import UserOnboarding

MAX_STEP = 3


def get_or_create_onboarding(user) -> UserOnboarding:
    ob, _ = UserOnboarding.objects.get_or_create(user=user)
    return ob


def user_has_active_projects(user) -> bool:
    return Project.objects.filter(owner=user, is_deleted=False).exists()


def auto_complete_legacy_onboarding(user, ob: UserOnboarding) -> bool:
    """
    Students who already had projects before the guided wizard should not see it again.
    City/mobile can be collected later from profile — do not block the dashboard.
    """
    if ob.completed_at or ob.skipped:
        return False
    if not user_has_active_projects(user):
        return False
    ob.completed_at = timezone.now()
    ob.step_completed = max(ob.step_completed, MAX_STEP)
    ob.save(update_fields=['completed_at', 'step_completed'])
    return True


def sync_onboarding_progress(user) -> UserOnboarding:
    """Align wizard step with profile/projects (do not auto-finish from old deploys)."""
    ob = get_or_create_onboarding(user)
    if ob.skipped or ob.completed_at:
        return ob

    if auto_complete_legacy_onboarding(user, ob):
        return ob

    step = ob.step_completed
    if profile_is_complete(user):
        step = max(step, 1)
    elif step >= 1:
        step = 0
    if user_has_active_projects(user):
        step = max(step, 2)

    if step != ob.step_completed:
        ob.step_completed = step
        ob.save(update_fields=['step_completed'])
    return ob


def should_show_onboarding(user) -> bool:
    if not user.is_authenticated:
        return False
    ob = sync_onboarding_progress(user)
    if ob.completed_at or ob.skipped:
        return False
    if user_has_active_projects(user):
        return False
    return True


def current_wizard_step(ob: UserOnboarding) -> int:
    """Active step number (1–3) for the modal UI."""
    if ob.step_completed >= MAX_STEP:
        return MAX_STEP
    return min(ob.step_completed + 1, MAX_STEP)


def advance_step(ob: UserOnboarding, step: int) -> None:
    if step > ob.step_completed:
        ob.step_completed = step
        ob.save(update_fields=['step_completed'])


def skip_onboarding(user) -> UserOnboarding:
    ob = get_or_create_onboarding(user)
    if not profile_is_complete(user):
        return ob
    ob.skipped = True
    if not ob.completed_at:
        ob.completed_at = timezone.now()
    ob.save(update_fields=['skipped', 'completed_at'])
    return ob


def complete_onboarding(user) -> UserOnboarding:
    ob = get_or_create_onboarding(user)
    if not ob.completed_at:
        ob.completed_at = timezone.now()
    ob.step_completed = max(ob.step_completed, MAX_STEP)
    ob.save(update_fields=['completed_at', 'step_completed'])
    return ob


def complete_onboarding_on_deploy(user) -> None:
    complete_onboarding(user)
