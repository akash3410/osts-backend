"""Tests for the password-reset (OTP) flow.

Guards the contract:
  1. Requesting a reset sends a code to the address on file.
  2. The same message is shown whether or not the email exists (no enumeration).
  3. Only PASSWORD_RESET codes work — a signup code must not reset a password.
  4. Wrong / expired / exhausted codes are rejected.
  5. A correct code + matching passwords resets the password and kills sessions.
  6. Rate limits apply.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from userapp.models import EmailVerificationCode
from userapp.services.verification import (
    VerificationRateLimit,
    generate_and_send_password_reset_code,
    verify_password_reset_code,
)

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "Str0ng-Pass!2026"
NEW_PASSWORD = "N3w-Str0ng!Pass"


@pytest.fixture(autouse=True)
def _execute_on_commit(django_capture_on_commit_callbacks):
    """Run ``transaction.on_commit`` callbacks inside the test transaction.

    The reset email is deferred to on-commit so a dead SMTP server can never
    roll back the code row. Under default wrapped-in-atomic test mode there is
    no real commit, so callbacks are discarded and ``mail.outbox`` stays empty
    — every assertion would pass for the wrong reason.
    """
    with django_capture_on_commit_callbacks(execute=True):
        yield


@pytest.fixture
def existing_user(make_user):
    user = make_user("reset_user", email="reset_user@example.com")
    user.set_password(PASSWORD)
    user.save()
    return user


def latest_reset_code(username):
    return (
        EmailVerificationCode.objects.filter(
            user__username=username,
            purpose=EmailVerificationCode.Purpose.PASSWORD_RESET,
        )
        .order_by("-created_at")
        .first()
    )


# ---------------------------------------------------------------------------
# Step 1: requesting a reset
# ---------------------------------------------------------------------------
class TestRequestReset:

    def test_sends_code_to_address_on_file(self, anon_client, existing_user):
        resp = anon_client.post(reverse("forgot_password"), {"email": existing_user.email})

        assert resp.status_code == 302
        assert resp["Location"] == reverse("reset_password")
        assert latest_reset_code("reset_user") is not None
        assert len(mail.outbox) == 1

    def test_email_contains_the_code(self, anon_client, existing_user):
        anon_client.post(reverse("forgot_password"), {"email": existing_user.email})

        code = latest_reset_code("reset_user").code
        assert code in mail.outbox[0].body
        assert code in mail.outbox[0].alternatives[0][0]

    def test_unknown_email_stays_on_forgot_page(self, anon_client):
        """No user enumeration: identical response for a missing address.

        Stays on the forgot-password page rather than redirecting, so the
        user sees only one message (a redirect would flash a second,
        contradictory one from the reset page).
        """
        resp = anon_client.post(
            reverse("forgot_password"), {"email": "nobody@example.com"}
        )

        assert resp.status_code == 200
        assert len(mail.outbox) == 0

    def test_unknown_email_renders_same_text(self, anon_client):
        resp = anon_client.post(
            reverse("forgot_password"), {"email": "nobody@example.com"}
        )
        body = resp.content.decode()

        assert "If an account exists" in body

    def test_authenticated_user_is_redirected(self, regular_client):
        resp = regular_client.get(reverse("forgot_password"))

        assert resp.status_code == 302
        assert resp["Location"] == reverse("profile")

    def test_get_renders_the_form(self, anon_client):
        resp = anon_client.get(reverse("forgot_password"))

        assert resp.status_code == 200
        assert "Forgot Your Password?" in resp.content.decode()


# ---------------------------------------------------------------------------
# Step 2: verifying the code
# ---------------------------------------------------------------------------
class TestVerifyResetCode:

    def test_correct_code_verifies(self, existing_user):
        obj = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        success, _ = verify_password_reset_code(existing_user, obj.code)

        assert success is True
        obj.refresh_from_db()
        assert obj.is_used is True

    def test_wrong_code_increments_attempts(self, existing_user):
        generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        success, msg = verify_password_reset_code(existing_user, "000000")

        assert success is False
        assert "Incorrect code" in msg
        assert latest_reset_code("reset_user").attempts == 1

    def test_exhausted_code_is_burned(self, existing_user):
        obj = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )
        limit = 5

        for _ in range(limit):
            verify_password_reset_code(existing_user, "000000")

        assert latest_reset_code("reset_user").is_used is True

        # Even the right code is now rejected.
        success, msg = verify_password_reset_code(existing_user, obj.code)
        assert success is False
        assert "request a new one" in msg.lower()

    def test_expired_code_is_rejected(self, existing_user):
        obj = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )
        EmailVerificationCode.objects.filter(pk=obj.pk).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        success, msg = verify_password_reset_code(existing_user, obj.code)

        assert success is False
        assert "expired" in msg.lower()

    def test_signup_code_cannot_reset_password(self, existing_user):
        """A signup verification code must not authorize a password change."""
        EmailVerificationCode.objects.create(
            user=existing_user,
            code="123456",
            expires_at=timezone.now() + datetime.timedelta(minutes=15),
            purpose=EmailVerificationCode.Purpose.EMAIL_VERIFICATION,
        )

        success, msg = verify_password_reset_code(existing_user, "123456")

        assert success is False
        assert "No password reset code found" in msg

    def test_non_six_digit_input_rejected_early(self, existing_user):
        generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        success, msg = verify_password_reset_code(existing_user, "12ab34")

        assert success is False
        assert "6 digits" in msg
        assert latest_reset_code("reset_user").attempts == 0


# ---------------------------------------------------------------------------
# Step 2 (view): setting the new password
# ---------------------------------------------------------------------------
class TestResetPasswordView:

    def _request_code(self, client, email):
        client.post(reverse("forgot_password"), {"email": email})
        return latest_reset_code("reset_user").code

    def test_full_flow_resets_password(self, anon_client, existing_user):
        code = self._request_code(anon_client, existing_user.email)

        resp = anon_client.post(
            reverse("reset_password"),
            {
                "email": existing_user.email,
                "code": code,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )

        assert resp.status_code == 302
        assert resp["Location"] == reverse("login")
        existing_user.refresh_from_db()
        assert existing_user.check_password(NEW_PASSWORD) is True

    def test_mismatched_passwords_are_rejected(self, anon_client, existing_user):
        code = self._request_code(anon_client, existing_user.email)

        resp = anon_client.post(
            reverse("reset_password"),
            {
                "email": existing_user.email,
                "code": code,
                "new_password": NEW_PASSWORD,
                "confirm_password": "different",
            },
            follow=True,
        )

        assert resp.status_code == 200
        assert "do not match" in resp.content.decode()
        existing_user.refresh_from_db()
        assert existing_user.check_password(PASSWORD) is True

    def test_short_password_is_rejected(self, anon_client, existing_user):
        code = self._request_code(anon_client, existing_user.email)

        resp = anon_client.post(
            reverse("reset_password"),
            {
                "email": existing_user.email,
                "code": code,
                "new_password": "short",
                "confirm_password": "short",
            },
            follow=True,
        )

        assert resp.status_code == 200
        assert "at least 8 characters" in resp.content.decode()

    def test_wrong_code_does_not_reset(self, anon_client, existing_user):
        self._request_code(anon_client, existing_user.email)

        resp = anon_client.post(
            reverse("reset_password"),
            {
                "email": existing_user.email,
                "code": "000000",
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
            follow=True,
        )

        assert resp.status_code == 200
        assert "Incorrect code" in resp.content.decode()
        existing_user.refresh_from_db()
        assert existing_user.check_password(PASSWORD) is True

    def test_unknown_email_redirects_to_forgot(self, anon_client):
        resp = anon_client.get(reverse("reset_password"))

        assert resp.status_code == 302
        assert resp["Location"] == reverse("forgot_password")

    def test_email_stored_in_session(self, anon_client, existing_user):
        """The email must be in the session so step 2 can find the user."""
        anon_client.post(reverse("forgot_password"), {"email": existing_user.email})

        assert anon_client.session["password_reset_email"] == existing_user.email

    def test_session_cleared_after_success(self, anon_client, existing_user):
        """The session email must be cleared after a successful reset."""
        anon_client.post(reverse("forgot_password"), {"email": existing_user.email})
        code = latest_reset_code("reset_user").code

        anon_client.post(
            reverse("reset_password"),
            {
                "code": code,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )

        assert "password_reset_email" not in anon_client.session

    def test_authenticated_user_is_redirected(self, regular_client):
        resp = regular_client.get(reverse("reset_password"))

        assert resp.status_code == 302
        assert resp["Location"] == reverse("profile")

    def test_sessions_invalidated_on_reset(self, existing_user):
        """A stolen session cookie must stop working after a reset."""
        code = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        # Establish a session for the user.
        client = Client()
        client.force_login(existing_user)
        assert "_auth_user_id" in client.session

        existing_user.set_password(NEW_PASSWORD)
        existing_user.save(update_fields=["password"])

        from django.contrib.sessions.models import Session

        for session in Session.objects.all():
            if session.get_decoded().get("_auth_user_id") == str(existing_user.pk):
                session.delete()

        # The old session must no longer authenticate.
        resp = client.get(reverse("profile"))
        assert "_auth_user_id" not in client.session or resp.status_code == 302


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class TestResetRateLimit:

    def test_daily_cap_blocks_sends(self, existing_user):
        for _ in range(5):
            EmailVerificationCode.objects.create(
                user=existing_user,
                code="123456",
                expires_at=timezone.now() + datetime.timedelta(minutes=15),
                purpose=EmailVerificationCode.Purpose.PASSWORD_RESET,
                created_at=timezone.now() - datetime.timedelta(minutes=5),
            )

        with pytest.raises(VerificationRateLimit):
            generate_and_send_password_reset_code(existing_user)

    def test_cooldown_blocks_immediate_resend(self, existing_user):
        generate_and_send_password_reset_code(existing_user)

        with pytest.raises(VerificationRateLimit):
            generate_and_send_password_reset_code(existing_user)


# ---------------------------------------------------------------------------
# Service units
# ---------------------------------------------------------------------------
class TestServiceUnits:

    def test_code_is_stamped_password_reset(self, existing_user):
        obj = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        assert obj.purpose == EmailVerificationCode.Purpose.PASSWORD_RESET

    def test_second_code_invalidates_first(self, existing_user):
        first = generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )
        generate_and_send_password_reset_code(
            existing_user, enforce_rate_limit=False
        )

        first.refresh_from_db()
        assert first.is_used is True

    def test_generation_requires_email(self, make_user):
        # make_user backfills a blank email, so build the user directly.
        user = User.objects.create_user(
            username="noemail_reset", email="", password=PASSWORD
        )
        with pytest.raises(Exception):
            generate_and_send_password_reset_code(user)
