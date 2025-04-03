from django.shortcuts import render, redirect
from dashboardapp.models import Service
from .forms import MessageForm
from django.contrib import messages

# Create your views here.
def home_view(request):
    services = Service.objects.filter(is_active=True)

    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Message Sent!")
            return redirect(request.path + "#send-message")
    else:
        form = MessageForm()

    context = {
        'services': services,
        'form': form,
    }

    return render(request, 'myapp/index.html', context)


def about_view(request):
    return render(request, 'myapp/about.html')

def service_view(request):
    return render(request, 'myapp/service.html')

def contact_view(request):
    return render(request, 'myapp/contact.html')