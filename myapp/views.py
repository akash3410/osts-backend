from django.shortcuts import render
from dashboardapp.models import Service

# Create your views here.
def home_view(request):
    services = Service.objects.filter(is_active=True)

    context = {
        'services': services
    }
    return render(request, 'myapp/index.html', context)


def about_view(request):
    return render(request, 'myapp/about.html')

def service_view(request):
    return render(request, 'myapp/service.html')

def contact_view(request):
    return render(request, 'myapp/contact.html')