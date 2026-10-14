from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.signals import pre_social_login
from django.dispatch import receiver

User = get_user_model()


def _deny(request, text):
    """Attach an error message (best effort) and abort the social login."""
    try:
        messages.error(request, text)
    except Exception:
        # Message storage may be unavailable in some contexts; still block.
        pass
    raise ImmediateHttpResponse(redirect("login"))


@receiver(pre_social_login)
def restrict_social_login(sender, request, sociallogin, **kwargs):
    """
    Enforce the same access rules as the regular login view:

    - Only staff/superuser accounts are allowed to log in.
    - New accounts cannot be created via social sign-up (registration is
      superuser-only in this project). If the social email matches an
      already-registered user, the social account is linked to it so future
      social logins work directly.
    """
    user = sociallogin.user
    email = (user.email or "").strip() if user else ""

    existing = None
    if user and user.pk:
        existing = user
    elif email:
        existing = User.objects.filter(email__iexact=email).first()

    if existing is None:
        _deny(
            request,
            "Access denied! Your account must be created by an administrator first.",
        )

    if not (existing.is_staff or existing.is_superuser):
        _deny(request, "Access denied!")

    # Link the social account to the existing user so that the next social
    # login is matched directly.
    if not sociallogin.is_existing:
        sociallogin.connect(request, existing)
