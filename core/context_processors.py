from .models import SiteConfiguration

def site_configuration(request):
    return { 'site_config': SiteConfiguration.objects.first() }