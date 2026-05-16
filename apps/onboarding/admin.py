from django.contrib import admin

from .models import UserOnboarding


@admin.register(UserOnboarding)
class UserOnboardingAdmin(admin.ModelAdmin):
    list_display = ('user', 'step_completed', 'skipped', 'completed_at')
    list_filter = ('skipped', 'step_completed')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)
