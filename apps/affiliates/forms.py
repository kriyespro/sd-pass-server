from django import forms

from .models import AffiliateApplication


class AffiliateApplicationForm(forms.ModelForm):
    class Meta:
        model = AffiliateApplication
        fields = ['name', 'email', 'website', 'platform', 'audience_size', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com', 'readonly': 'readonly'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yourchannel.com'}),
            'audience_size': forms.TextInput(attrs={'placeholder': 'e.g. 5000 or 10k'}),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell us how you plan to promote Krizn…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].disabled = True

    def clean(self):
        cleaned = super().clean()
        user = getattr(self.instance, 'user', None)
        if user and AffiliateApplication.objects.filter(
            user=user,
            status=AffiliateApplication.Status.PENDING,
        ).exclude(pk=self.instance.pk or None).exists():
            raise forms.ValidationError('You already have a pending application.')
        if user and AffiliateApplication.objects.filter(
            user=user,
            status=AffiliateApplication.Status.APPROVED,
        ).exclude(pk=self.instance.pk or None).exists():
            raise forms.ValidationError('You are already an approved affiliate.')
        return cleaned
