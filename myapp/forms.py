from django import forms
from .models import Messages
from dashboardapp.models import Service
from phonenumber_field.formfields import PhoneNumberField

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
    class Meta:
        model = Messages
        fields = ['name', 'email', 'phone', 'service', 'note']