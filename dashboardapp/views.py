from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from .forms import ServiceForm
from .models import Service

# Create your views here.
def superuser_or_staff_required(user):
    return user.is_superuser or user.is_staff

@user_passes_test(superuser_or_staff_required)
def dashboard_view(request):
    return render(request, "dashboardapp/dashboard.html")

@user_passes_test(superuser_or_staff_required)
def service_view(request):
    services = Service.objects.all()
    return render(request, 'dashboardapp/services.html', {'services': services})

@user_passes_test(superuser_or_staff_required)
def add_service(request):
    form_for = "Add New Services"
    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('service')
    else:
        form = ServiceForm()

    context = {
        'form': form,
        'form_for': form_for,
    }
    return render(request, 'dashboardapp/addserviceForm.html', context)

@user_passes_test(superuser_or_staff_required)
def edit_service(request, pk):
    form_for = "Edit Service"
    service = get_object_or_404(Service, pk=pk)

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            form.save()
            return redirect('service')
    else:
        form = ServiceForm(instance=service)

    context = {
        'form': form,
        'form_for': form_for,
    }
    return render(request, 'dashboardapp/addserviceForm.html', context)

@user_passes_test(superuser_or_staff_required)
def delete_service(request, pk):
    service = get_object_or_404(Service, pk=pk)

    service.delete()
    return redirect('service')