from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.conf import settings
from django.views.decorators.http import require_POST
from .forms import LoginForm, RegisterForm, UserInfoForm, UpdateUserForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Userinfo

# Create your views here.
def supperuser_required(user):
    return user.is_superuser

def superuser_or_staffuser_required(user):
    return user.is_superuser or user.is_staff


def auth_page(request):
    """Combined Sign Up / Log In page with a tab toggle."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    active_tab = request.GET.get('tab', 'signup')
    if active_tab not in ('signup', 'login'):
        active_tab = 'signup'

    login_form = LoginForm()
    signup_form = RegisterForm()

    if request.method == 'POST':
        if request.POST.get('form_type') == 'login':
            active_tab = 'login'
            login_form = LoginForm(request, data=request.POST)
            if login_form.is_valid():
                user = login_form.get_user()
                if user.is_staff:
                    login(request, user)
                    return redirect('dashboard')
                messages.error(request, "Access denied!")
                return redirect('/user/auth/?tab=login')
        else:
            active_tab = 'signup'
            signup_form = RegisterForm(request.POST)
            if signup_form.is_valid():
                signup_form.save()
                messages.success(
                    request,
                    "Account created successfully! You can now log in.",
                )
                active_tab = 'login'

    return render(request, 'userapp/auth.html', {
        'login_form': login_form,
        'signup_form': signup_form,
        'active_tab': active_tab,
    })


def register_view(request):
    """Legacy URL — signup now lives on the combined auth page."""
    return redirect('/user/auth/?tab=signup')

def login_view(request):
    """Legacy URL — login now lives on the combined auth page."""
    return redirect('/user/auth/?tab=login')

@require_POST
@login_required
def logout_view(request):
    # POST-only logout (OWASP): a GET logout is a CSRF vector — a third-party
    # site can log a user out with a hidden request or an <img> tag.
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)

@user_passes_test(superuser_or_staffuser_required)
def edit_user_info(request):
    user = request.user

    if not hasattr(user, 'userinfo'):
        Userinfo.objects.create(user=user)

    if request.method == 'POST':
        form = UserInfoForm(request.POST, request.FILES, instance=user.userinfo)
        userform = UpdateUserForm(request.POST, instance=user)
        if form.is_valid() and userform.is_valid():
            form.save()
            userform.save()
            return redirect('dashboard')
    else:
        form = UserInfoForm(instance=user.userinfo)
        userform = UpdateUserForm(instance=user)
    return render(request, 'userapp/editUserInfo.html', {'form': form, 'userform': userform})

@user_passes_test(superuser_or_staffuser_required)
def profile_view(request):
    return render(request, 'userapp/profile.html')