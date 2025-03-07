from django import forms
from .models import Service

class ServiceForm(forms.ModelForm):
    title = forms.CharField(
        label="Title",
        widget=forms.TextInput(attrs={'placeholder': "Service title here...", 'class': "form-control"})
    )
    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={
            'placeholder': "Describe your service...",
            'class': "form-control",
            'rows': 5,
            'cols': 50,
        })
    )
    price = forms.DecimalField(
        label="Price",
        widget=forms.NumberInput(attrs={'placeholder': "Price in BDT...", 'class': "form-control"})
    )
    image = forms.ImageField(
        label="Service Image",
        widget=forms.ClearableFileInput(attrs={'class': "form-control"})
    )
    icon = forms.CharField(
        label="Icon",
        widget=forms.TextInput(attrs={'placeholder': "Icon link here...", 'class': "form-control"}),
        required=False
    )
    is_active = forms.BooleanField(
        label="Is Active?",
        widget=forms.CheckboxInput(attrs={'class': "form-check-input"}),
        required=False
    )
    class Meta:
        model = Service
        fields = ['title', 'description', 'icon', 'image', 'price', 'is_active']