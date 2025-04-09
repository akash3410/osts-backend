from django.contrib.auth.decorators import user_passes_test
from .models import SiteConfiguration
from myapp.models import Messages

def site_configuration(request):
    return { 'site_config': SiteConfiguration.objects.first() }

def message_in_box(request):
    messages = Messages.objects.filter(response=False).order_by("-created_at")
    return { 'messagesbox': messages }