import re

from django import forms

from .models import EnvVar

_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)


class EnvVarForm(forms.ModelForm):
    value = forms.CharField(
        label='Value',
        widget=forms.Textarea(attrs={'rows': 3}),
        required=True,
    )

    class Meta:
        model = EnvVar
        fields = ('key',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _name, field in self.fields.items():
            field.widget.attrs.setdefault('class', _FIELD_CLASS)

    def clean_key(self):
        key = (self.cleaned_data.get('key') or '').strip()
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            raise forms.ValidationError('Use letters, numbers, underscore; start with letter or underscore.')
        return key

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.set_plaintext(self.cleaned_data['value'])
        if commit:
            instance.save()
        return instance
