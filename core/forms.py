from django import forms
from .models import SiteConfiguration
from phonenumber_field.formfields import PhoneNumberField

class SiteConfigForm(forms.ModelForm):
    site_name = forms.CharField(
        label="Site Name",
        widget=forms.TextInput(attrs={'placeholder': "Your site name", 'class': "form-control"})
    )

    site_mail = forms.EmailField(
        label="Site Email",
        widget=forms.EmailInput(attrs={'placeholder': "Your Site Email", 'class': "form-control"})
    )
    site_phone = PhoneNumberField(
        label="Site Phone",
        widget=forms.TextInput(attrs={'placeholder': "Your site phone number", 'class': "form-control"})
    )
    site_address = forms.CharField(
        label="Site Address",
        widget=forms.TextInput(attrs={'placeholder': "Your Address", 'class': "form-control"})
    )    
    fb_page = forms.URLField(
        label="Page Link",
        widget=forms.URLInput(attrs={'placeholder': "Facebook page link", 'class': "form-control"})
    )
    linkedIn = forms.URLField(
        label="Page Link",
        widget=forms.URLInput(attrs={'placeholder': "LinkedIn page link", 'class': "form-control"})
    )
    contact_description = forms.CharField(
        label="Contact Description",
        widget=forms.Textarea(attrs={
            'placeholder': "Your Contact Description", 
            'class': "form-control",
            'rows': 5,
            'cols': 50,
        })
    )
    site_bg = forms.ImageField(
        label="Site Background",
        widget=forms.ClearableFileInput(attrs={'class': "form-control"})
    )
    site_logo = forms.ImageField(
        label="Site Logo",
        widget=forms.ClearableFileInput(attrs={'class': "form-control"})
    )

    fact_title = forms.CharField(
        label="Fact Title",
        widget=forms.TextInput(attrs={'placeholder': "Fact title", 'class': "form-control"})
    )
    fact_description = forms.CharField(
        label="Fact Description",
        widget=forms.Textarea(attrs={
            'placeholder': "Your site name",
            'class': "form-control",
            'rows': 5,
            'cols': 50,
        })
    )

    about_title = forms.CharField(
        label="About Title",
        widget=forms.TextInput(attrs={'placeholder': "About title", 'class': "form-control"})
    )
    about_description = forms.CharField(
        label="About Description",
        widget=forms.Textarea(attrs={
            'placeholder': "About Description",
            'class': "form-control",
            'rows': 5,
            'cols': 50
        })
    )
    about_image = forms.ImageField(
        label="Site Background",
        widget=forms.ClearableFileInput(attrs={'class': "form-control"})
    )

    maintenance_mode = forms.BooleanField(
        label="Want to maintainens?",
        widget=forms.CheckboxInput(attrs={'class': "form-check-input"})
    )

    class Meta:
        model = SiteConfiguration
        fields = '__all__'

    def clean(self):
        """Ensure only one instance exists."""
        if SiteConfiguration.objects.exists() and not self.instance.pk:
            raise forms.ValidationError("Only one SiteConfiguration instance can exist.")
        return super().clean()