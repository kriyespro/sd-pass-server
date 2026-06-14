from django import forms

from .models import EmailCampaign, EmailList, EmailTemplate, ScheduledEmail, SMTPConfig


class EmailTemplateForm(forms.ModelForm):
    class Meta:
        model = EmailTemplate
        fields = ['template_type', 'subject', 'html_body', 'is_active']
        widgets = {
            'html_body': forms.Textarea(attrs={'rows': 20, 'class': 'font-mono text-sm'}),
            'subject': forms.TextInput(attrs={'placeholder': 'e.g. Your receipt for {{plan_name}}'}),
        }


class SMTPConfigForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))

    class Meta:
        model = SMTPConfig
        fields = ['host', 'port', 'username', 'password', 'use_tls', 'from_email', 'from_name', 'is_active']


class TestEmailForm(forms.Form):
    to_email = forms.EmailField(label='Send test to', help_text='Email address to receive the test')


class EmailListForm(forms.ModelForm):
    class Meta:
        model = EmailList
        fields = ['name', 'description', 'emails']
        widgets = {
            'emails': forms.Textarea(attrs={'rows': 12, 'placeholder': 'user@example.com\nanother@example.com'}),
            'description': forms.TextInput(attrs={'placeholder': 'Optional description'}),
        }


class ScheduledEmailForm(forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        help_text='Optional — use Send Now on the list page to skip scheduling.',
    )

    class Meta:
        model = ScheduledEmail
        fields = ['template', 'email_list', 'to_emails', 'scheduled_at']
        widgets = {
            'to_emails': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('email_list') and not cleaned.get('to_emails'):
            raise forms.ValidationError('Select an email list or enter recipient emails.')
        if not cleaned.get('scheduled_at'):
            from django.utils import timezone
            cleaned['scheduled_at'] = timezone.now()
        return cleaned


class EmailCampaignForm(forms.ModelForm):
    next_run_at = forms.DateTimeField(
        required=True,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        label='First send at',
    )

    class Meta:
        model = EmailCampaign
        fields = ['name', 'template', 'email_list', 'frequency', 'next_run_at', 'is_active']
