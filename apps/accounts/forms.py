from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django import forms

from .models import User

_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)


class EmailAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Email'
        for _name, field in self.fields.items():
            field.widget.attrs.setdefault('class', _FIELD_CLASS)


class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)
    mobile = forms.CharField(required=False, max_length=32)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'mobile', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _name, field in self.fields.items():
            classes = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (classes + ' ' + _FIELD_CLASS).strip()
