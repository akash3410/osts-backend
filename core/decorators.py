"""
Role-based access decorators.

Single source of truth for "who may enter". Replaces the four duplicated
``superuser_or_staff_required`` helpers that were scattered across views.

Usage:
    @owner_required           # superuser OR member of the 'owner' Group
    @staff_required           # is_staff flag (Django-admin access)
    @employee_required        # member of the 'employee' Group
    @client_required          # member of the 'client' Group
    @login_required_only      # any authenticated user

All redirect anonymous users to LOGIN_URL and authenticated-but-unauthorized
users to the redirect target (default: the site home) rather than raising a
500 — a normal user hitting a staff URL should get a friendly bounce, not a
stack trace.
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied

from userapp.models import User

# Where to send an authenticated user who lacks the required role.
UNAUTHORIZED_REDIRECT = settings.LOGIN_URL


def _role_test(role_name):
    """Build a predicate: superuser always passes, otherwise check the Group."""

    def test(user):
        # Anonymous users always fail (user_passes_test handles the redirect).
        if not user.is_authenticated:
            return False
        # Superusers bypass every role check.
        if user.is_superuser:
            return True
        return user.has_role(role_name)

    return test


def _staff_test(user):
    if not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser


owner_required = user_passes_test(_role_test(User.ROLE_OWNER))
staff_required = user_passes_test(_staff_test)
employee_required = user_passes_test(_role_test(User.ROLE_EMPLOYEE))
client_required = user_passes_test(_role_test(User.ROLE_CLIENT))


def roles_required(*roles, redirect_to=None):
    """Allow any of the named roles (superuser always allowed).

    Example:
        @roles_required(User.ROLE_EMPLOYEE, User.ROLE_OWNER)
        def my_view(request): ...
    """

    def test(user):
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return any(user.has_role(r) for r in roles)

    decorator = user_passes_test(test, login_url=redirect_to or settings.LOGIN_URL)
    return decorator


def owner_or_employee_required(view_func):
    """Convenience: owner OR employee may pass."""
    return roles_required(User.ROLE_OWNER, User.ROLE_EMPLOYEE)(view_func)
