from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

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