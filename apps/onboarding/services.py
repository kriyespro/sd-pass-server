from django.utils import timezone

from apps.projects.models import Project

from .models import UserOnboarding

MAX_STEP = 3


def get_or_create_onboarding(user) -> UserOnboarding:
    ob, _ = UserOnboarding.objects.get_or_create(user=user)
    return ob


def sync_onboarding_progress(user) -> UserOnboarding:
    """Align wizard step with profile/projects (do not auto-finish from old deploys)."""
    ob = get_or_create_onboarding(user)
    if ob.skipped or ob.completed_at:
        return ob

    step = ob.step_completed
    if (user.first_name or '').strip() and (user.last_name or '').strip():
        step = max(step, 1)
    if Project.objects.filter(owner=user, is_deleted=False).exists():
        step = max(step, 2)

    if step != ob.step_completed:
        ob.step_completed = step
        ob.save(update_fields=['step_completed'])
    return ob


def should_show_onboarding(user) -> bool:
    if not user.is_authenticated:
        return False
    ob = sync_onboarding_progress(user)
    return not ob.skipped and ob.completed_at is None


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
