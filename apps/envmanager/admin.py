from django.contrib import admin

from .models import EnvVar


@admin.register(EnvVar)
class EnvVarAdmin(admin.ModelAdmin):
    list_display = ('key', 'project', 'has_value')
    search_fields = ('key', 'project__slug')

    @admin.display(boolean=True)
    def has_value(self, obj):
        return bool(obj.value_ciphertext)
