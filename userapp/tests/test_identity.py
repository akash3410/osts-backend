"""Tests for the Phase 2 identity foundation: custom User, role helpers,
Profile/Client/Employee models, Groups, and the role decorators."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from core.decorators import (
    client_required,
    employee_required,
    owner_required,
    roles_required,
    staff_required,
)
from userapp.models import Client, Employee, Profile, Skill

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Custom User model
# ---------------------------------------------------------------------------
class TestCustomUser:
    def test_auth_user_model_is_custom(self):
        assert User._meta.label == "userapp.User"

    def test_str_returns_username(self, make_user):
        u = make_user("alice")
        assert str(u) == "alice"

    def test_duplicate_email_rejected(self, make_user):
        make_user("u1", email="same@example.com")
        with pytest.raises(Exception):
            make_user("u2", email="same@example.com")

    def test_blank_emails_allowed_for_legacy_rows(self, make_user):
        """6 legacy accounts have '' email — they must coexist."""
        a = make_user("blank1", email="")
        b = make_user("blank2", email="")
        assert User.objects.filter(pk=a.pk).exists()
        assert User.objects.filter(pk=b.pk).exists()

    def test_email_constraint_is_conditional(self):
        names = [c.name for c in User._meta.constraints]
        assert "user_email_unique_when_set" in names


# ---------------------------------------------------------------------------
# Role helpers (Group-backed)
# ---------------------------------------------------------------------------
class TestRoleHelpers:
    @pytest.fixture
    def roles(self):
        for name in ("client", "employee", "owner"):
            Group.objects.get_or_create(name=name)

    def test_has_role_membership(self, make_user, roles):
        u = make_user("member")
        assert not u.has_role("client")
        u.groups.add(Group.objects.get(name="client"))
        assert u.has_role("client")
        assert u.is_client
        assert not u.is_employee

    def test_is_owner_via_group(self, make_user, roles):
        u = make_user("boss")
        assert not u.is_owner
        u.groups.add(Group.objects.get(name="owner"))
        assert u.is_owner

    def test_superuser_is_always_owner(self, superuser):
        # No Group row needed — superuser short-circuits.
        assert superuser.is_owner

    def test_role_flags_default_false(self, regular_user, roles):
        assert not regular_user.is_client
        assert not regular_user.is_employee
        assert not regular_user.is_owner


# ---------------------------------------------------------------------------
# Profile / Client / Employee / Skill
# ---------------------------------------------------------------------------
class TestIdentityModels:
    def test_profile_created_and_linked(self, regular_user):
        p = Profile.objects.create(user=regular_user)
        assert p.user == regular_user
        assert regular_user.profile == p
        assert "Profile(" in str(p)

    def test_client_str_falls_back_to_username(self, regular_user):
        c = Client.objects.create(user=regular_user)
        assert str(c) == regular_user.username

    def test_client_str_prefers_company(self, regular_user):
        c = Client.objects.create(user=regular_user, company_name="Acme Ltd")
        assert str(c) == "Acme Ltd"

    def test_client_default_currency(self, regular_user):
        c = Client.objects.create(user=regular_user)
        assert c.currency == "BDT"

    def test_employee_skills_m2m(self, regular_user):
        e = Employee.objects.create(user=regular_user)
        s1 = Skill.objects.create(name="Django")
        s2 = Skill.objects.create(name="React")
        e.skills.add(s1, s2)
        assert e.skills.count() == 2
        assert regular_user.employee_profile == e

    def test_skill_name_unique(self):
        Skill.objects.create(name="Python")
        with pytest.raises(Exception):
            Skill.objects.create(name="Python")

    def test_skill_str_and_ordering(self):
        Skill.objects.create(name="Zebra")
        Skill.objects.create(name="Apple")
        assert [s.name for s in Skill.objects.all()] == ["Apple", "Zebra"]

    def test_timestamps_present(self, regular_user):
        p = Profile.objects.create(user=regular_user)
        assert p.created_at is not None
        assert p.updated_at is not None


# ---------------------------------------------------------------------------
# seed_roles command
# ---------------------------------------------------------------------------
class TestSeedRoles:
    def test_creates_three_role_groups(self):
        from django.core.management import call_command

        call_command("seed_roles")
        names = set(Group.objects.values_list("name", flat=True))
        assert {"client", "employee", "owner"} <= names

    def test_idempotent(self):
        from django.core.management import call_command

        call_command("seed_roles")
        call_command("seed_roles")
        # No duplicates created.
        assert Group.objects.filter(name="owner").count() == 1


# ---------------------------------------------------------------------------
# Role decorators
# ---------------------------------------------------------------------------
class TestRoleDecorators:
    @pytest.fixture
    def rf(self):
        return RequestFactory()

    @pytest.fixture
    def roles(self):
        for name in ("client", "employee", "owner"):
            Group.objects.get_or_create(name=name)

    @staticmethod
    def _run(decorator, user):
        """Run a decorator-wrapped view and return (allowed, response)."""

        @decorator
        def view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        from django.http import HttpRequest

        request = HttpRequest()
        request.user = user
        try:
            resp = view(request)
            return True, resp
        except Exception:
            return False, None

    def test_owner_required_allows_superuser(self, superuser):
        allowed, _ = self._run(owner_required, superuser)
        assert allowed

    def test_owner_required_blocks_regular_user(self, regular_user, roles, rf):
        # user_passes_test redirects (doesn't raise) — so we check the
        # redirect happens rather than a 200.
        @owner_required
        def view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        request = rf.get("/")
        request.user = regular_user
        resp = view(request)
        # Not allowed -> redirected to LOGIN_URL.
        assert resp.status_code == 302

    def test_owner_required_allows_group_member(self, make_user, roles):
        u = make_user("owner_member")
        u.groups.add(Group.objects.get(name="owner"))
        allowed, resp = self._run(owner_required, u)
        assert allowed and resp.status_code == 200

    def test_staff_required_checks_flag(self, staff_user, regular_user, rf):
        allowed, _ = self._run(staff_required, staff_user)
        assert allowed

        # regular user -> redirect
        @staff_required
        def view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        request = rf.get("/")
        request.user = regular_user
        assert view(request).status_code == 302

    def test_employee_and_client_decorators(self, make_user, roles):
        e = make_user("emp")
        e.groups.add(Group.objects.get(name="employee"))
        allowed, resp = self._run(employee_required, e)
        assert allowed and resp.status_code == 200

        c = make_user("cli")
        c.groups.add(Group.objects.get(name="client"))
        allowed, resp = self._run(client_required, c)
        assert allowed and resp.status_code == 200

    def test_roles_required_accepts_any(self, make_user, roles):
        u = make_user("multi")
        u.groups.add(Group.objects.get(name="client"))

        @roles_required("employee", "client")
        def view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        from django.http import HttpRequest

        request = HttpRequest()
        request.user = u
        assert view(request).status_code == 200

    def test_anonymous_fails_all(self, rf):
        from django.contrib.auth.models import AnonymousUser

        anon = AnonymousUser()
        for dec in (owner_required, staff_required, employee_required, client_required):
            @dec
            def view(request):
                from django.http import HttpResponse

                return HttpResponse("ok")

            request = rf.get("/")
            request.user = anon
            # Anonymous -> redirect to login (302), never allowed.
            assert view(request).status_code == 302


# ---------------------------------------------------------------------------
# Signup still creates a powerless account (regression w/ new User model)
# ---------------------------------------------------------------------------
class TestSignupOnCustomUser:
    def test_signup_creates_user_in_new_table(self, anon_client):
        payload = {
            "form_type": "signup",
            "username": "newuser_x",
            "first_name": "New",
            "last_name": "User",
            "email": "newuser_x@example.com",
            "password1": "Str0ng-Pass!2026",
            "password2": "Str0ng-Pass!2026",
        }
        anon_client.post(reverse("auth"), payload)
        u = User.objects.get(username="newuser_x")
        assert u.is_staff is False
        assert u.is_superuser is False
        assert not u.groups.exists()  # no role assigned on signup

    def test_signup_duplicate_email_shows_friendly_field_error(self, anon_client, make_user):
        make_user("existing_user", email="taken@example.com")
        payload = {
            "form_type": "signup",
            "username": "fresh_user",
            "first_name": "Fresh",
            "last_name": "User",
            "email": "taken@example.com",
            "password1": "Str0ng-Pass!2026",
            "password2": "Str0ng-Pass!2026",
        }
        resp = anon_client.post(reverse("auth"), payload)
        assert resp.status_code == 200
        form = resp.context["signup_form"]
        assert "email" in form.errors
        assert "already exists" in form.errors["email"][0]
        # Must NOT expose raw database constraint name
        assert "user_email_unique_when_set" not in resp.content.decode()
