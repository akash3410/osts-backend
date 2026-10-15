from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import Userinfo
from phonenumber_field.formfields import PhoneNumberField

class RegisterForm(UserCreationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={'placeholder': "Enter your username", 'class': "form-control auth-input", 'autocomplete': "username"})
    )
    first_name = forms.CharField(
        label="First Name",
        widget=forms.TextInput(attrs={'placeholder': "First Name", 'class': 'form-control auth-input'})
    )
    last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={'placeholder': "Last Name", 'class': 'form-control auth-input'})
    )
    email = forms.CharField(
        label="Email",
        widget=forms.EmailInput(attrs={'placeholder': "Enter Your Email", 'class': "form-control auth-input", 'autocomplete': "email"})
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Password", 'class': "form-control auth-input", 'autocomplete': "new-password"})
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Confirm Password", 'class': "form-control auth-input", 'autocomplete': "new-password"})
    )

    class Meta:
        model = User
        # NOTE: `is_staff` is deliberately NOT here. Staff/superuser status is
        # a privileged flag granted by an administrator (or the seed command),
        # never self-selected on a public signup form. See tests/test_auth.py.
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']

    def save(self, commit=True):
        """Force privileged flags off regardless of what lands in cleaned_data."""
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(attrs={'placeholder': "Enter your username", 'class': "form-control auth-input", 'autocomplete': "username"})
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': "Password", 'class': "form-control auth-input", 'autocomplete': "current-password"})
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

class UpdateUserForm(forms.ModelForm):
    first_name = forms.CharField(
        label="First Name",
        widget=forms.TextInput(attrs={'placeholder': "First Name", 'class': 'form-control'})
    )
    last_name = forms.CharField(
        label="Last Name",
        widget=forms.TextInput(attrs={'placeholder': "Last Name", 'class': 'form-control'})
    )
    class Meta:
        model = User
        fields = ['first_name', 'last_name']