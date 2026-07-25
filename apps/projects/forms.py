import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.billing.services import user_can_create_project_type, user_flask_limit, user_project_limit

from .models import Project, ProjectType
from .subdomain import allocate_unique_subdomain, subdomain_is_available, suggest_subdomain_base

_FIELD_CLASS = (
    'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 '
    'text-slate-100 outline-none ring-emerald-500/40 focus:border-emerald-500 focus:ring-2'
)

_LABEL_RE = re.compile(r'^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$')


def _validate_optional_fqdn(value: str) -> str:
    value = (value or '').strip().rstrip('.')
    if not value:
        return ''
    if len(value) > 253:
        raise ValidationError('That hostname is too long.')
    if '..' in value or '/' in value or ' ' in value or ':' in value:
        raise ValidationError('Use a plain hostname only (no URL, port, or path).')
    labels = value.split('.')
    if len(labels) < 2:
        raise ValidationError('Include a domain name, for example www.example.com.')
    for label in labels:
        if not _LABEL_RE.match(label):
            raise ValidationError(f'Invalid hostname segment: {label!r}.')
    return value.lower()


class ProjectCustomHostnameForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ('custom_hostname',)
        labels = {'custom_hostname': 'Public domain (optional)'}
        help_texts = {
            'custom_hostname': (
                'Visitors can open your site at this hostname after DNS points here and TXT '
                'verification succeeds (see instructions below). Leave blank to use only the platform subdomain.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fields['custom_hostname']
        f.required = False
        f.widget.attrs.setdefault('class', _FIELD_CLASS)
        f.widget.attrs.setdefault(
            'placeholder',
            'e.g. www.yourbrand.com',
        )

    def clean_custom_hostname(self):
        v = _validate_optional_fqdn(self.cleaned_data.get('custom_hostname') or '') or None
        if v:
            from apps.projects.host_allowlist import hostname_aliases
            aliases = hostname_aliases(v)
            qs = Project.objects.filter(is_deleted=False).exclude(pk=self.instance.pk)
            conflict = False
            for alias in aliases:
                if qs.filter(custom_hostname__iexact=alias).exists():
                    conflict = True
                    break
            if conflict:
                raise ValidationError(
                    'Another active project already uses this hostname '
                    '(including the www / non-www form).'
                )
        return v


class ProjectForm(forms.ModelForm):
    wp_admin_email = forms.EmailField(
        required=False,
        label='Admin email',
        help_text='Used to create your admin account. Only needed for WordPress and Drupal projects.',
    )

    class Meta:
        model = Project
        fields = ('name', 'project_type', 'subdomain', 'description')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.subdomain_adjusted_from = ''
        super().__init__(*args, **kwargs)
        self.order_fields(['name', 'project_type', 'subdomain', 'wp_admin_email', 'description'])
        if 'subdomain' in self.fields:
            self.fields['subdomain'].required = False
            self.fields['subdomain'].help_text = (
                'Optional — auto-generated from your project name or email if left blank. '
                'If taken, we assign the next available name (e.g. you-2). Letters, numbers, hyphens only.'
            )
            self.fields['subdomain'].widget.attrs['placeholder'] = 'e.g. my-portfolio (no spaces)'
        if 'description' in self.fields:
            self.fields['description'].required = False
            self.fields['description'].widget.attrs['placeholder'] = 'Short description (optional)'
        if 'name' in self.fields:
            self.fields['name'].widget.attrs['placeholder'] = 'My Portfolio Site'
        if 'project_type' in self.fields:
            flask_limit = user_flask_limit(user) if user else 0
            wp_allowed = user_can_create_project_type(user, 'wordpress') if user else False
            php_allowed = user_can_create_project_type(user, 'php') if user else False
            drupal_allowed = user_can_create_project_type(user, 'drupal') if user else False
            type_choices = [
                (ProjectType.STATIC, 'Static Website (HTML / CSS / JS / Tailwind)'),
                (ProjectType.FLASK,  f'Flask App (Python · SQLite){" — upgrade required" if flask_limit == 0 else ""}'),
                (ProjectType.WORDPRESS, f'WordPress{"" if wp_allowed else " — upgrade required"}'),
                (ProjectType.PHP, f'PHP App (upload a ZIP){"" if php_allowed else " — upgrade required"}'),
                (ProjectType.DRUPAL, f'Drupal{"" if drupal_allowed else " — upgrade required"}'),
            ]
            self.fields['project_type'].choices = type_choices
            self.fields['project_type'].initial = ProjectType.STATIC
            self.fields['project_type'].help_text = (
                'Static sites are fast and free to host. '
                'Flask apps, WordPress, PHP apps, and Drupal require WordPress Pro plan or higher.'
            )
        for _name, field in self.fields.items():
            field.widget.attrs.setdefault('class', _FIELD_CLASS)

    def clean_subdomain(self):
        raw = (self.cleaned_data.get('subdomain') or '').strip().lower()
        if not raw:
            return ''
        slug = slugify(raw)
        if not slug:
            raise forms.ValidationError('Use only letters, numbers, and hyphens.')
        if len(slug) > 200:
            raise forms.ValidationError('Subdomain is too long.')
        exclude_pk = self.instance.pk if self.instance and self.instance.pk else None
        if not subdomain_is_available(slug, exclude_pk=exclude_pk):
            suggested = allocate_unique_subdomain(slug, exclude_pk=exclude_pk)
            self.subdomain_adjusted_from = slug
            return suggested
        return slug

    def clean(self):
        data = super().clean()
        if self.user is None:
            return data

        # Total project limit
        limit = user_project_limit(self.user)
        count = Project.objects.filter(owner=self.user, is_deleted=False).count()
        if count >= limit:
            raise forms.ValidationError(
                f'You have reached your project limit ({limit} website{"s" if limit != 1 else ""}). '
                'Upgrade your plan with a coupon code to add more.'
            )

        # Flask-specific limit
        if data.get('project_type') == ProjectType.FLASK:
            flask_limit = user_flask_limit(self.user)
            if flask_limit == 0:
                raise forms.ValidationError(
                    'Flask app support requires WordPress Pro (₹3,699/year) or higher. '
                    'Upgrade your plan or add a Flask Add-on.'
                )
            flask_count = Project.objects.filter(
                owner=self.user, is_deleted=False, project_type=ProjectType.FLASK,
            ).count()
            if flask_count >= flask_limit:
                raise forms.ValidationError(
                    f'You have reached your Flask app limit '
                    f'({flask_limit} app{"s" if flask_limit != 1 else ""}). '
                    'Upgrade your plan or purchase a Flask Add-on.'
                )

        # WordPress-specific gate
        if data.get('project_type') == ProjectType.WORDPRESS:
            if not user_can_create_project_type(self.user, 'wordpress'):
                raise forms.ValidationError(
                    'WordPress hosting requires WordPress Pro (₹3,699/year) or higher. '
                    'Upgrade your plan to create a WordPress project.'
                )
            if not (data.get('wp_admin_email') or '').strip():
                raise forms.ValidationError('Enter an admin email for your WordPress site.')

        # PHP-specific gate
        if data.get('project_type') == ProjectType.PHP:
            if not user_can_create_project_type(self.user, 'php'):
                raise forms.ValidationError(
                    'PHP app hosting requires WordPress Pro (₹3,699/year) or higher. '
                    'Upgrade your plan to create a PHP project.'
                )

        # Drupal-specific gate
        if data.get('project_type') == ProjectType.DRUPAL:
            if not user_can_create_project_type(self.user, 'drupal'):
                raise forms.ValidationError(
                    'Drupal hosting requires WordPress Pro (₹3,699/year) or higher. '
                    'Upgrade your plan to create a Drupal project.'
                )
            if not (data.get('wp_admin_email') or '').strip():
                raise forms.ValidationError('Enter an admin email for your Drupal site.')

        return data
