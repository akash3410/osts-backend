"""
Create placeholder SocialApplication records so the auth page renders
(and the social buttons are shown) even before real OAuth credentials are
configured.

Real credentials can be filled in later with:
    python manage.py seed_social_apps
or via the Django admin (/admin/socialaccount/socialapp/add).
"""
from django.db import migrations

PLACEHOLDER_APPS = [
    {'provider': 'google', 'name': 'Google'},
    {'provider': 'facebook', 'name': 'Facebook'},
    {'provider': 'apple', 'name': 'Apple'},
]


def create_placeholder_apps(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')

    site = Site.objects.get_current()

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
