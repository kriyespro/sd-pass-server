from django import forms

from apps.accounts.models import User
from apps.projects.forms import ProjectForm
_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)


class OnboardingNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', _FIELD_CLASS)


class OnboardingProjectForm(ProjectForm):
    """First project during onboarding — name only; subdomain auto-generated."""

    class Meta(ProjectForm.Meta):
        fields = ('name',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.setdefault('placeholder', 'My Portfolio Site')

