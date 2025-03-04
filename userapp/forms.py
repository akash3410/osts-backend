from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Userinfo
from phonenumber_field.formfields import PhoneNumberField

class RegisterForm(UserCreationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={'placeholder': "Enter your username", 'class': "form-control"})
    )
    first_name = forms.CharField(
        label="First Name",
        widget=forms.TextInput(attrs={'placeholder': "First Name", 'class': 'form-control'})
    )
    last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={'placeholder': "Last Name", 'class': 'form-control'})
    )
    email = forms.CharField(
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': "Enter a valid email", 'class': "form-control"})
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Enter your password", 'class': "form-control"})
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Confirm your password", 'class': "form-control"})
    )
    is_staff = forms.BooleanField(
        required=False,
        label="IS Staff ?",
        widget=forms.CheckboxInput(attrs={'class': "form-check-input"})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2', 'is_staff']


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={'placeholder': "Enter your username", 'class': "form-control"})
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Enter your password", 'class': "form-control"})
    )

class UserInfoForm(forms.ModelForm):
    phone = PhoneNumberField(
        label="Phone Number",
        widget=forms.TextInput(attrs={'placeholder': "Your Phone", 'class': "form-control"}),
        required = False
    )
    secondary_email = forms.CharField(
        label="Secondary Email",
        widget=forms.EmailInput(attrs={'placeholder': "Example: xyz@example.com", 'class': "form-control"})
    )
    present_address = forms.CharField(
        label="Present Address",
        widget=forms.TextInput(attrs={'placeholder': "Your Present Address", 'class': "form-control"})
    )
    permanent_address = forms.CharField(
        label="Permanent Address",
        widget=forms.TextInput(attrs={'placeholder': "Your Permanent Address", 'class': "form-control"})
    )
    profile_picture = forms.ImageField(
        label="Profile Picture",
        widget=forms.FileInput(attrs={'class': "form-control"})
    )
    cover_photo = forms.ImageField(
        label="Cover Photo",
        widget=forms.FileInput(attrs={'class': "form-control"})
    )
    class Meta:
        model = Userinfo
        fields = ['phone', 'secondary_email', 'present_address', 'permanent_address', 'profile_picture', 'cover_photo']