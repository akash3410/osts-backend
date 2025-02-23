from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .forms import LoginForm, RegisterForm
from django.contrib.auth.decorators import login_required, user_passes_test

# Create your views here.
def supperuser_required(user):
    return user.is_superuser


def dashboard_view(request):
    return render(request, 'userapp/dashboard.html')

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
        return redirect('homepage')
    
    if request.method == "POST":
        form = LoginForm(data = request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("homepage")
    else:
        form = LoginForm()
    return render(request, "userapp/loginForm.html", {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')


