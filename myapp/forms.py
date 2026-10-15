from django import forms
from .models import Inquiry
from dashboardapp.models import Service
from phonenumber_field.formfields import PhoneNumberField

# Honeypot field name. Deliberately innocuous-sounding ("website" / "url") so
# a spam bot autofills it; a human never sees or touches it because it is
# hidden via CSS in the template. If it comes back non-empty, it's a bot.
HONEYPOT_FIELD = "website_url"


class MessageForm(forms.ModelForm):
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'placeholder': "Your Name",
            'class': "form-control border-0",
            'style': "height: 55px",
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'placeholder': "Your Email",
            'class': "form-control border-0",
            'style': "height: 55px",
        })
    )
    phone = PhoneNumberField(
        widget=forms.TextInput(attrs={
            'placeholder': "Ex: +8801xxxxxxxxx",
            'class': "form-control border-0",
            'style': "height: 55px",
        })
    )
    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True),
        empty_label="Select a Service",
        widget=forms.Select(attrs={
            'placeholder': "Ex: +8801xxxxxxxxx",
            'class': "form-control border-0",
            'style': "height: 55px",
        })
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': "Special note",
            'class': "form-control border-0",
            'style': "height: 55px",
            'rows': 2,
            'cols': 20,
        })
    )
    # Honeypot: hidden from humans, tempting to bots. Not a model field, so it
    # is never saved — it only exists to catch automated submissions.
    website_url = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'style': 'display:none !important;',
            'tabindex': '-1',
            'autocomplete': 'off',
            'aria-hidden': 'true',
        }),
    )

    class Meta:
        model = Inquiry
        fields = ['name', 'email', 'phone', 'service', 'note']

    def clean_website_url(self):
        """Reject the submission if the honeypot was filled in."""
        if self.cleaned_data.get(HONEYPOT_FIELD):
            # Raise a generic error so we don't tip off the bot that it was
            # caught; the field is hidden so a human will never see this.
            raise forms.ValidationError("Invalid submission.")
        return ""