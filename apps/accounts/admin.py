from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User
from .services import deactivate_user_account


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'mobile', 'is_staff', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'mobile')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    actions = ('deactivate_accounts', 'reactivate_accounts')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {'fields': ('first_name', 'last_name', 'mobile')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('email', 'first_name', 'last_name', 'mobile', 'password1', 'password2'),
            },
        ),
    )

    readonly_fields = ('last_login', 'date_joined')

    @admin.action(description='Deactivate — remove sites, block login (recommended)')
    def deactivate_accounts(self, request, queryset):
        count = 0
        for user in queryset:
            if user.is_superuser:
                self.message_user(
                    request,
                    f'Skipped superuser {user.email}.',
                    level=messages.WARNING,
                )
                continue
            if user.is_active:
                deactivate_user_account(user)
                count += 1
        self.message_user(
            request,
            f'Deactivated {count} account(s). Students cannot log in; projects and files were removed.',
        )

    @admin.action(description='Reactivate — allow login again (does not restore deleted sites)')
    def reactivate_accounts(self, request, queryset):
        updated = queryset.filter(is_superuser=False).update(is_active=True)
        self.message_user(
            request,
            f'Reactivated {updated} account(s). They must create projects and upload again.',
        )

    def delete_model(self, request, obj):
        if obj.is_superuser:
            super().delete_model(request, obj)
            return
        deactivate_user_account(obj)
        self.message_user(
            request,
            f'Deactivated {obj.email} (not permanently deleted). Sites removed; login blocked. '
            'Use “Reactivate” to allow sign-in again.',
            level=messages.WARNING,
        )

    def delete_queryset(self, request, queryset):
        count = 0
        for obj in queryset:
            if obj.is_superuser:
                continue
            deactivate_user_account(obj)
            count += 1
        self.message_user(
            request,
            f'Deactivated {count} account(s). Permanent delete is disabled for students.',
            level=messages.WARNING,
        )

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser:
            return super().has_delete_permission(request, obj)
        return True
