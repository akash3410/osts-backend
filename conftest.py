"""Shared pytest fixtures for the OSTS test suite."""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Sites framework (required by django-allauth)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Seed the ``Site`` row that allauth's ``get_current()`` requires.

    pytest-django builds a fresh test database from migrations. The sites
    migration creates the *table* but no row, and ``SITE_ID = 1`` makes
    allauth call ``Site.objects.get_current()`` -> ``Site.DoesNotExist`` the
    moment any auth/social template renders. We create the row once per
    session, right after migrations run.
    """
    from django.contrib.sites.models import Site

    with django_db_blocker.unblock():
        Site.objects.update_or_create(
            pk=1,
            defaults={
                "domain": "example.com",
                "name": "OSTS (test)",
            },
        )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@pytest.fixture
def make_user(db):
    """Factory for users with an explicit role."""

    def _make(username, *, staff=False, superuser=False, email=None, password="Str0ng-Pass!2026"):
        user = User.objects.create_user(
            username=username,
            email=email or f"{username}@example.com",
            password=password,
        )
        if staff:
            user.is_staff = True
        if superuser:
            user.is_staff = True
            user.is_superuser = True
        user.save()
        return user

    return _make


@pytest.fixture
def anon_user():
    """Anonymous client is the default; named for readability."""
    return None


@pytest.fixture
def regular_user(make_user):
    return make_user("visitor1")


@pytest.fixture
def staff_user(make_user):
    return make_user("staff1", staff=True)


@pytest.fixture
def superuser(make_user):
    return make_user("owner1", superuser=True)


# ---------------------------------------------------------------------------
# Authenticated clients
# ---------------------------------------------------------------------------
@pytest.fixture
def anon_client(db):
    from django.test import Client

    return Client()


@pytest.fixture
def staff_client(staff_user):
    from django.test import Client

    c = Client()
    c.force_login(staff_user)
    return c


@pytest.fixture
def superuser_client(superuser):
    from django.test import Client

    c = Client()
    c.force_login(superuser)
    return c


@pytest.fixture
def regular_client(regular_user):
    from django.test import Client

    c = Client()
    c.force_login(regular_user)
    return c


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------
@pytest.fixture
def make_service(db):
    from dashboardapp.models import Service

    def _make(title="Web Dev", **overrides):
        defaults = {"description": "A service", "is_active": True}
        defaults.update(overrides)
        return Service.objects.create(title=title, **defaults)

    return _make


@pytest.fixture
def service(make_service):
    return make_service()


@pytest.fixture
def make_message(db):
    from myapp.models import Inquiry

    def _make(name="Client", **overrides):
        # `service` is now an FK (was free text). Default to a real Service
        # unless the caller supplies one (or explicitly passes None).
        if "service" not in overrides:
            from dashboardapp.models import Service

            overrides["service"] = (
                Service.objects.filter(is_active=True).first()
                or Service.objects.create(title="Web", description="A service")
            )
        defaults = {
            "email": "client@example.com",
            "note": "Hello",
        }
        defaults.update(overrides)
        return Inquiry.objects.create(name=name, **defaults)

    return _make


@pytest.fixture
def message(make_message):
    return make_message()
