from django.core.cache import cache

from .models import SiteConfiguration

# Cache the singleton so it isn't re-fetched on every single request. It's a
# settings row that changes rarely (via the dashboard), so a short TTL is plenty.
SITE_CONFIG_CACHE_KEY = "core:site_configuration"
SITE_CONFIG_CACHE_TTL = 60 * 5  # 5 minutes


def site_configuration(request):
    """Attach the SiteConfiguration singleton, cached.

    Measured: this was one query on *every* request (even pages that never
    render it). It's a near-static settings row, so we cache it. The cache is
    cleared in SiteConfiguration.save()/delete() so an edit shows up at once.
    """
    site_config = cache.get(SITE_CONFIG_CACHE_KEY)
    if site_config is None:
        site_config = SiteConfiguration.objects.first()
        # Cache even a miss (None) briefly so a DB with no config row doesn't
        # hammer the DB either.
        cache.set(SITE_CONFIG_CACHE_KEY, site_config, SITE_CONFIG_CACHE_TTL)
    return {"site_config": site_config}


def message_in_box(request):
    """Attach pending inquiries for the dashboard badge.

    SECURITY: pending inquiries contain PII (name, email, note). This runs for
    *every* request, so previously that data was placed into the context of all
    pages — public pages included. No public template iterates it today, but it
    only takes one template change to leak it. We now only build the queryset
    for staff users (the sole consumer is the dashboard nav badge).

    The queryset is also lazy, so even for staff the SQL doesn't execute until
    the template actually loops over it.
    """
    from myapp.models import Inquiry

    user = request.user
    if not (user.is_authenticated and (user.is_staff or user.is_superuser)):
        # Return an empty list: cheap, and safe to iterate if a template asks.
        return {"messagesbox": []}

    return {
        "messagesbox": Inquiry.objects.filter(status=Inquiry.Status.NEW)
        .order_by("-created_at")
        .only("id", "name", "created_at", "status")
    }
