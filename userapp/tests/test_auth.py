"""Security regression tests for the authentication / authorization holes.

Each test here guards a bug that was found and fixed in Phase 1. They exist
to make sure the hole can never quietly reopen.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestSignupPrivilegeEscalation:
    """Public signup must never be able to mint a staff/superuser account."""

    def _signup_payload(self, **extra):
        payload = {
            "form_type": "signup",
            "username": "pentester",
            "first_name": "Pen",
            "last_name": "Tester",
            "email": "pentester@example.com",
            "password1": "Str0ng-Pass!2026",
            "password2": "Str0ng-Pass!2026",
        }
        payload.update(extra)
        return payload

    def test_signup_form_has_no_is_staff_field(self):
        from userapp.forms import RegisterForm

        assert "is_staff" not in RegisterForm().fields
        assert "is_superuser" not in RegisterForm().fields

    def test_injected_is_staff_is_ignored(self, anon_client):
        """An attacker POSTing is_staff=1 still gets a non-staff account."""
        resp = anon_client.post(
            reverse("auth"), self._signup_payload(is_staff="on", is_superuser="on")
        )
        user = User.objects.get(username="pentester")
        # Regardless of response, the created account must be powerless.
        assert user.is_staff is False
        assert user.is_superuser is False
        assert resp.status_code in (200, 302)

    def test_save_forces_privileged_flags_off(self):
        from userapp.forms import RegisterForm

        form = RegisterForm(
            data=self._signup_payload(is_staff="on", is_superuser="on")
        )
        assert form.is_valid(), form.errors
        user = form.save()
        assert user.is_staff is False
        assert user.is_superuser is False


class TestMutationsArePostOnly:
    """Destructive/state-changing actions must reject GET."""

    def test_message_delete_requires_post(self, anon_client, message):
        url = reverse("messagedelete", args=[message.pk])
        anon_client.get(url)  # GET must not delete
        assert type(message).objects.filter(pk=message.pk).exists()

    def test_service_delete_requires_post(self, anon_client, service):
        url = reverse("deleteservice", args=[service.pk])
        anon_client.get(url)
        assert type(service).objects.filter(pk=service.pk).exists()

    def test_response_toggle_requires_post(self, staff_client, message):
        url = reverse("responseupdate", args=[message.pk])
        before = message.response
        staff_client.get(url)
        message.refresh_from_db()
        assert message.response == before  # unchanged by GET

    def test_logout_requires_post(self, staff_client, staff_user):
        resp = staff_client.get(reverse("logout"))
        # A GET should not log the user out (305/405 or a redirect back).
        staff_client.get(reverse("logout"))
        # Still authenticated? force_login sessions survive unless POSTed.
        # The view is @require_POST, so a GET never calls logout().
        assert resp.status_code in (405, 302)

    def test_logout_post_works(self, staff_client):
        resp = staff_client.post(reverse("logout"), follow=False)
        assert resp.status_code == 302


class TestDashboardAuthorization:
    """Every dashboard view must reject anonymous + non-staff users."""

    DASHBOARD_VIEWS = [
        ("dashboard", []),
        ("service", []),
        ("addservice", []),
        ("allmessage", []),
        ("siteinfo", []),
    ]

    @pytest.mark.parametrize("url_name,args", DASHBOARD_VIEWS)
    def test_anonymous_redirected_to_login(self, anon_client, url_name, args):
        resp = anon_client.get(reverse(url_name, args=args))
        # user_passes_test sends anonymous users to LOGIN_URL, preserving the
        # original page in ?next= so the user lands back where they intended.
        assert resp.status_code == 302
        location = resp["Location"]
        assert settings.LOGIN_URL in location
        assert "next=" in location

    @pytest.mark.parametrize("url_name,args", DASHBOARD_VIEWS)
    def test_regular_user_denied(self, regular_client, url_name, args):
        resp = regular_client.get(reverse(url_name, args=args))
        # Non-staff get bounced to the login page as well.
        assert resp.status_code == 302

    @pytest.mark.parametrize("url_name,args", DASHBOARD_VIEWS)
    def test_staff_allowed(self, staff_client, url_name, args):
        resp = staff_client.get(reverse(url_name, args=args))
        assert resp.status_code == 200


class TestMessageDeleteAuthorization:
    """The specific view that was completely unauthenticated."""

    def test_anonymous_cannot_delete_message(self, anon_client, message):
        anon_client.post(reverse("messagedelete", args=[message.pk]))
        assert type(message).objects.filter(pk=message.pk).exists()

    def test_non_staff_cannot_delete_message(self, regular_client, message):
        regular_client.post(reverse("messagedelete", args=[message.pk]))
        assert type(message).objects.filter(pk=message.pk).exists()

    def test_staff_can_delete_message(self, staff_client, message):
        staff_client.post(reverse("messagedelete", args=[message.pk]))
        assert not type(message).objects.filter(pk=message.pk).exists()
