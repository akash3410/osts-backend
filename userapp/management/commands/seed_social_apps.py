"""
Seed SocialApplication records (django-allauth) from environment variables.

Usage:
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
    FACEBOOK_CLIENT_ID=... FACEBOOK_CLIENT_SECRET=... \
    APPLE_CLIENT_ID=... APPLE_CLIENT_SECRET=... APPLE_KEY_ID=... \
    python manage.py seed_social_apps

Each provider is only seeded when its credentials are present in the
environment. Existing apps (matched by provider + client_id) are updated, not
duplicated.
"""
import os

from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialApp


PROVIDERS = {
    'google': {
        'client_id': 'GOOGLE_CLIENT_ID',
        'secret': 'GOOGLE_CLIENT_SECRET',
        'key': None,
    },
    'facebook': {
        'client_id': 'FACEBOOK_CLIENT_ID',
        'secret': 'FACEBOOK_CLIENT_SECRET',
        'key': None,
    },
    'apple': {
        'client_id': 'APPLE_CLIENT_ID',
        'secret': 'APPLE_CLIENT_SECRET',
        'key': 'APPLE_KEY_ID',
    },
}


class Command(BaseCommand):
    help = 'Create/update allauth SocialApp records from environment variables.'

    def handle(self, *args, **options):
        site = Site.objects.get_current()

        for provider, env in PROVIDERS.items():
            client_id = os.environ.get(env['client_id'], '').strip()
            secret = os.environ.get(env['secret'], '').strip()
            key_env = env['key']
            key = os.environ.get(key_env, '').strip() if key_env else ''

            if not client_id or not secret:
                self.stdout.write(
                    self.style.WARNING(
                        f'Skipping {provider}: set {env["client_id"]} and '
                        f'{env["secret"]} in the environment.'
                    )
                )
                continue

            app, created = SocialApp.objects.update_or_create(
                provider=provider,
                defaults={'name': provider.title(), 'client_id': client_id, 'secret': secret, 'key': key},
            )
            app.sites.add(site)

            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f'{action} SocialApp for {provider} (client_id={client_id[:8]}…)'
            ))
