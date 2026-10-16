from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Profile
from .utils import generate_username_suggestions
from phonenumber_field.formfields import PhoneNumberField

User = get_user_model()

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
    email = forms.EmailField(
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.username_suggestions = []

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            return username
        if User.objects.filter(username__iexact=username).exists():
            fn = self.data.get("first_name", "")
            ln = self.data.get("last_name", "")
            suggestions = generate_username_suggestions(username, first_name=fn, last_name=ln, count=4)
            self.username_suggestions = suggestions
            msg = "This username is already taken."
            if suggestions:
                msg += f" Available suggestions: {', '.join(suggestions)}"
            raise forms.ValidationError(msg, code="duplicate_username")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email address already exists. Please log in."
            )
        return email

    def save(self, commit=True):
        """Force privileged flags off regardless of what lands in cleaned_data."""
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.is_active = False  # Account stays inactive until email verification
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
        model = Profile
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