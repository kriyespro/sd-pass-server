import re

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.services import normalize_mobile
from apps.projects.forms import ProjectForm
from apps.projects.subdomain import suggest_subdomain_base

_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)


class OnboardingProfileForm(forms.ModelForm):
    """Step 1 — name (from Google or manual), city, and mobile."""

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'city', 'mobile')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['city'].required = True
        self.fields['mobile'].required = True
        self.fields['city'].widget.attrs.setdefault('placeholder', 'e.g. Jaipur')
        self.fields['mobile'].widget.attrs.setdefault('placeholder', 'e.g. +91 98765 43210')
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', _FIELD_CLASS)

    def clean_city(self):
        city = (self.cleaned_data.get('city') or '').strip()
        if len(city) < 2:
            raise ValidationError('Enter your city.')
        if len(city) > 120:
            raise ValidationError('City name is too long.')
        return city

    def clean_mobile(self):
        raw = (self.cleaned_data.get('mobile') or '').strip()
        if not raw:
            raise ValidationError('Mobile number is required.')
        normalized = normalize_mobile(raw)
        digits = re.sub(r'\D', '', normalized)
        if len(digits) < 10 or len(digits) > 15:
            raise ValidationError('Enter a valid mobile number (10–15 digits).')
        return normalized


class OnboardingProjectForm(ProjectForm):
    """First project during onboarding — name only; subdomain auto-generated."""

    class Meta(ProjectForm.Meta):
        fields = ('name',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('placeholder', 'My Portfolio Site')

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user and not (instance.subdomain or '').strip():
            instance.subdomain = suggest_subdomain_base(self.user, instance.name)
        if commit:
            instance.save()
        return instance
