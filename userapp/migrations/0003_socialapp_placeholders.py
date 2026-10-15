"""
Create placeholder SocialApplication records so the auth page renders
(and the social buttons are shown) even before real OAuth credentials are
configured.

Real credentials can be filled in later with:
    python manage.py seed_social_apps
or via the Django admin (/admin/socialaccount/socialapp/add).
"""
from django.conf import settings
from django.db import migrations

PLACEHOLDER_APPS = [
    {'provider': 'google', 'name': 'Google'},
    {'provider': 'facebook', 'name': 'Facebook'},
    {'provider': 'apple', 'name': 'Apple'},
]


def create_placeholder_apps(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')

    # Do NOT call Site.objects.get_current() here. That helper reads SITE_ID
    # and raises Site.DoesNotExist if the row is missing. The default
    # `example.com` Site is normally created by django.contrib.sites'
    # *post_migrate* handler, which runs only AFTER every migration has
    # finished — so on a fresh database (or a test DB built from scratch)
    # this data migration executes *before* that row exists. Make the
    # migration self-sufficient: grab the configured site, creating it if it
    # isn't there yet.
    site_id = getattr(settings, 'SITE_ID', 1)
    site, _ = Site.objects.get_or_create(
        pk=site_id,
        defaults={'domain': 'example.com', 'name': 'example.com'},
    )

    for spec in PLACEHOLDER_APPS:
        app, created = SocialApp.objects.get_or_create(
            provider=spec['provider'],
            defaults={
                'name': spec['name'],
                'client_id': f'{spec["provider"]}-not-configured',
                'secret': 'not-configured',
            },
        )
        app.sites.add(site)


def remove_placeholder_apps(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    SocialApp.objects.filter(
        client_id__in=[f'{p["provider"]}-not-configured' for p in PLACEHOLDER_APPS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_alter_domain_unique'),
        ('socialaccount', '0006_alter_socialaccount_extra_data'),
        ('userapp', '0002_alter_userinfo_user'),
    ]

    operations = [
        migrations.RunPython(create_placeholder_apps, remove_placeholder_apps),
    ]
