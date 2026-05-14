"""Who counts as a trainer and which students they may supervise (read-only audit)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q


def is_trainer(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.students.models import Batch, StudentProfile

    if Batch.objects.filter(trainer=user).exists():
        return True
    return StudentProfile.objects.filter(trainer=user).exists()


def trainee_users_queryset(trainer):
    """Users supervised via batch membership or direct StudentProfile.trainer."""
    from apps.students.models import StudentProfile

    User = get_user_model()
    return User.objects.filter(
        Q(pk__in=StudentProfile.objects.filter(trainer=trainer).values("user_id"))
        | Q(batches__trainer=trainer)
    ).distinct()
