from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .forms import LoginForm, RegisterForm, UserInfoForm, UpdateUserForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Userinfo

# Create your views here.
def supperuser_required(user):
    return user.is_superuser

def superuser_or_staffuser_required(user):
    return user.is_superuser or user.is_staff

@user_passes_test(supperuser_required)
def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, "userapp/registerForm.html", {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == "POST":
        form = LoginForm(request, data = request.POST)
        if form.is_valid():
            user = form.get_user()
            if user.is_staff:
                login(request, user)
                return redirect("dashboard")
            else:
                messages.error(request, "Access denied!")
                return redirect('login')
    else:
        form = LoginForm()
    return render(request, "userapp/loginForm.html", {'form': form})

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

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