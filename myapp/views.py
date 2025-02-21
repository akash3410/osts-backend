from django.shortcuts import render

# Create your views here.
def home_view(request):
    return render(request, 'myapp/index.html')


def about_view(request):
    return render(request, 'myapp/about.html')

def service_view(request):
    return render(request, 'myapp/service.html')

def contact_view(request):
    return render(request, 'myapp/contact.html')