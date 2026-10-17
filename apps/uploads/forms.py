from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from .models import ProjectUpload


def _validate_zip_size(uploaded):
    if uploaded.size > settings.STUDENT_UPLOAD_MAX_BYTES:
        raise ValidationError(
            f'ZIP must be {settings.STUDENT_UPLOAD_MAX_BYTES // (1024 * 1024)} MB or smaller.'
        )


class ZipUploadForm(forms.ModelForm):
    class Meta:
        model = ProjectUpload
        fields = ('file',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['file']
        field.validators.append(FileExtensionValidator(['zip']))
        field.validators.append(_validate_zip_size)
        field.widget.attrs.setdefault(
            'class',
            'block w-full cursor-pointer rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-500 file:px-3 file:py-1 file:text-slate-950',
        )


class MultiStaticUploadForm(forms.Form):
    """CSRF + non-field errors only; files come from request.FILES.getlist('files')."""

    pass


_TEXT_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)


class GithubPullForm(forms.Form):
    repo_url = forms.CharField(
        label='GitHub repo',
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': _TEXT_FIELD_CLASS,
            'placeholder': 'https://github.com/owner/repo or owner/repo',
        }),
    )
    branch = forms.CharField(
        label='Branch',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': _TEXT_FIELD_CLASS,
            'placeholder': "main (leave blank for the repo's default branch)",
        }),
    )

    def clean_repo_url(self):
        from apps.uploads.github_pull import parse_github_repo

        value = self.cleaned_data['repo_url']
        if not parse_github_repo(value):
            raise ValidationError(
                'Enter a GitHub repo URL (e.g. https://github.com/owner/repo) or owner/repo.'
            )
        return value
