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
