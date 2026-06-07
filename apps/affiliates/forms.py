from django import forms

from .models import AffiliateApplication


class AffiliateApplicationForm(forms.ModelForm):
    class Meta:
        model = AffiliateApplication
        fields = ['name', 'email', 'website', 'platform', 'audience_size', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yourchannel.com'}),
            'audience_size': forms.TextInput(attrs={'placeholder': 'e.g. 5000 or 10k'}),
            'message': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Tell us how you plan to promote Krizn…'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if AffiliateApplication.objects.filter(email=email).exists():
            raise forms.ValidationError('An application with this email already exists.')
        return email
