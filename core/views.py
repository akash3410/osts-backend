from django.shortcuts import render, redirect
from .forms import SiteConfigForm
from .models import SiteConfiguration
from django.contrib.auth.decorators import user_passes_test

# Create your views here.
def required_is_supper_or_is_staff(user):
    return user.is_superuser or user.is_staff

@user_passes_test(required_is_supper_or_is_staff)
def site_config(request):
    config = SiteConfiguration.objects.first()

    if request.method == "POST":
        form = SiteConfigForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            return redirect('siteinfo')
        
    form = SiteConfigForm(instance=config)
    return render(request, 'core/siteconfigForm.html', {'form': form})
