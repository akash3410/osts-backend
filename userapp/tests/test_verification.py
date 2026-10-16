"""End-to-end tests for the email-verification (OTP) signup flow.

The contract these guard:

  1. Signup creates an *inactive* account and routes to the OTP page.
  2. Exactly one live code exists; older ones are burned.
  3. The email is actually delivered, with the code, to the right address.
  4. The OTP page never shows the raw email address.
  5. Wrong / expired / exhausted codes never activate an account.
  6. A correct code activates the account and authenticates the session.
  7. Sends are rate-limited per user (cooldown + daily cap).
  8. SMTP failure degrades to a logged error, never a 500.

Without this file the flow had zero coverage: it is the only path between a
visitor and a logged-in user, so a silent regression here locks everyone out.
"""

import datetime

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from userapp.models import EmailVerificationCode
from userapp.services.verification import (
    VerificationRateLimit,
    generate_and_send_verification_code,
    mask_email,
    verify_user_code,
)

User = get_user_model()

# ``transaction=True`` is load-bearing, not a speed/style preference.
#
# The signup flow defers the email send to ``transaction.on_commit`` so a
# dead SMTP server can never roll back an already-created account. Under the
# default (wrapped-in-atomic) Django test mode there is no real commit, so
# on-commit callbacks are discarded and the emails would silently never
# send — every assertion against ``mail.outbox`` would see an empty list and
# pass for the wrong reason. Real transactions make the code under test
# behave exactly as it does in production.
pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "Str0ng-Pass!2026"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------
def signup_payload(**extra):
    payload = {
        "form_type": "signup",
        "username": "otp_user",
        "first_name": "Otp",
        "last_name": "User",
        "email": "otp_user@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    payload.update(extra)
    return payload


def do_signup(client, **extra):
    return client.post(reverse("auth"), signup_payload(**extra))


def latest_code_for(username):
    return (
        EmailVerificationCode.objects.filter(user__username=username)
        .order_by("-created_at")
        .first()
    )


def make_code(user, *, created_at=None, expires_at=None, is_used=False, code="123456"):
    """Create a code row, backdating it if asked.

    ``created_at`` is ``auto_now_add`` so it cannot be passed to
    ``create()`` — the value would be silently discarded and the row would
    look brand new. We set it with a follow-up ``update()``, which bypasses
    ``auto_now_add`` the way real time-travel in tests requires.
    """
    obj = EmailVerificationCode.objects.create(
        user=user,
        code=code,
        expires_at=expires_at or (timezone.now() + datetime.timedelta(minutes=15)),
        is_used=is_used,
    )
    if created_at is not None:
        EmailVerificationCode.objects.filter(pk=obj.pk).update(created_at=created_at)
        obj.refresh_from_db()
    return obj


@pytest.fixture
def inactive_user(make_user):
    """A user parked pre-verification, exactly as signup leaves them."""
    user = make_user("otp_user", email="otp_user@example.com")
    user.is_active = False
    user.save()
    return user


# ---------------------------------------------------------------------------
# 1-3: signup -> inactive + code + email
# ---------------------------------------------------------------------------
class TestSignupHandsOffToVerification:

    def test_signup_creates_inactive_user_and_redirects(self, anon_client):
        resp = do_signup(anon_client)

        assert resp.status_code == 302
        assert resp["Location"] == reverse("verify_email")

        user = User.objects.get(username="otp_user")
        assert user.is_active is False
        # Not authenticated — verification is the gate.
        assert "_auth_user_id" not in anon_client.session

    def test_signup_persists_a_code(self, anon_client):
        do_signup(anon_client)

        code = latest_code_for("otp_user")
        assert code is not None
        assert len(code.code) == 6
        assert code.code.isdigit()
        assert code.is_used is False
        assert code.is_valid() is True

    def test_signup_sends_exactly_one_email_to_the_right_address(self, anon_client):
        do_signup(anon_client)

        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.to == ["otp_user@example.com"]
        # Both a plain-text and an HTML alternative must be present; some
        # clients render only one or the other.
        assert message.body
        assert message.alternatives, "HTML alternative missing"

    def test_email_contains_the_persisted_code(self, anon_client):
        do_signup(anon_client)

        stored = latest_code_for("otp_user").code
        message = mail.outbox[0]
        assert stored in message.body
        assert stored in message.alternatives[0][0]

    def test_signup_stores_masked_email_in_the_session_page(self, anon_client):
        """The rendered OTP page must not leak the full address."""
        do_signup(anon_client)
        resp = anon_client.get(reverse("verify_email"))

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "o******r@example.com" in content
        assert "otp_user@example.com" not in content

    def test_flash_message_is_masked_too(self, anon_client):
        """Regression: the success message used to print the raw address."""
        do_signup(anon_client)
        resp = anon_client.get(reverse("verify_email"))

        assert "otp_user@example.com" not in resp.content.decode()

    def test_code_is_invisible_to_the_page_context(self, anon_client):
        """The OTP page must not render the code it is asking for."""
        do_signup(anon_client)
        resp = anon_client.get(reverse("verify_email"))

        stored = latest_code_for("otp_user").code
        assert stored not in resp.content.decode()


# ---------------------------------------------------------------------------
# 5-6: verification outcomes
# ---------------------------------------------------------------------------
class TestCodeVerification:

    def test_correct_code_activates_and_logs_in(self, anon_client):
        do_signup(anon_client)
        code = latest_code_for("otp_user").code

        resp = anon_client.post(reverse("verify_email"), {"code": code})

        assert resp.status_code == 302
        assert resp["Location"] == reverse("profile")

        user = User.objects.get(username="otp_user")
        assert user.is_active is True
        assert anon_client.session["_auth_user_id"] == str(user.pk)
        # The code is single-use.
        assert latest_code_for("otp_user").is_used is True

    def test_wrong_code_does_not_activate(self, anon_client):
        do_signup(anon_client)

        resp = anon_client.post(reverse("verify_email"), {"code": "000000"})

        assert resp.status_code == 200
        assert "Incorrect verification code" in resp.content.decode()
        assert User.objects.get(username="otp_user").is_active is False
        assert "_auth_user_id" not in anon_client.session

    def test_wrong_code_increments_attempts(self, anon_client):
        do_signup(anon_client)
        anon_client.post(reverse("verify_email"), {"code": "000000"})

        assert latest_code_for("otp_user").attempts == 1

    def test_attempts_are_reported_as_remaining(self, anon_client):
        do_signup(anon_client)
        resp = anon_client.post(reverse("verify_email"), {"code": "000000"})

        content = resp.content.decode()
        limit = settings.EMAIL_VERIFICATION_MAX_ATTEMPTS
        assert f"{limit - 1} attempts remaining" in content

    def test_exhausted_code_is_burned(self, anon_client):
        """After N wrong guesses the code is dead, not merely counted."""
        do_signup(anon_client)
        limit = settings.EMAIL_VERIFICATION_MAX_ATTEMPTS

        for _ in range(limit):
            anon_client.post(reverse("verify_email"), {"code": "000000"})

        code = latest_code_for("otp_user")
        assert code.attempts == limit
        assert code.is_used is True

        # Even the *right* code is now rejected, and it must say so rather
        # than "incorrect" so the user knows to resend.
        correct = code.code
        resp = anon_client.post(reverse("verify_email"), {"code": correct})
        assert "already been used" in resp.content.decode().lower()
        assert User.objects.get(username="otp_user").is_active is False

    def test_expired_code_is_rejected(self, anon_client):
        do_signup(anon_client)
        code = latest_code_for("otp_user")
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            expires_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        resp = anon_client.post(reverse("verify_email"), {"code": code.code})

        assert "expired" in resp.content.decode().lower()
        assert User.objects.get(username="otp_user").is_active is False

    def test_non_six_digit_input_is_rejected_early(self, anon_client):
        """Short-circuits before touching the code row."""
        do_signup(anon_client)

        resp = anon_client.post(reverse("verify_email"), {"code": "12ab34"})

        assert "6 digits" in resp.content.decode()
        assert latest_code_for("otp_user").attempts == 0

    def test_empty_code_is_rejected(self, anon_client):
        do_signup(anon_client)

        resp = anon_client.post(reverse("verify_email"), {"code": "   "})

        assert resp.status_code == 200
        assert "Please enter the 6-digit verification code" in resp.content.decode()


# ---------------------------------------------------------------------------
# 2: only one live code at a time
# ---------------------------------------------------------------------------
class TestSingleLiveCode:

    def test_resend_burns_the_previous_code(self, anon_client):
        do_signup(anon_client)
        first = latest_code_for("otp_user")
        first_code = first.code

        # Jump past the cooldown so the resend is allowed.
        EmailVerificationCode.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=5)
        )
        resp = anon_client.post(reverse("resend_code"), follow=True)
        assert resp.status_code == 200

        second = latest_code_for("otp_user")
        assert second.pk != first.pk
        first.refresh_from_db()
        assert first.is_used is True
        assert second.code != first_code

    def test_only_the_newest_code_works(self, anon_client):
        do_signup(anon_client)
        first = latest_code_for("otp_user")
        old_code = first.code

        EmailVerificationCode.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=5)
        )
        anon_client.post(reverse("resend_code"), follow=True)

        # The superseded code must not activate the account — it is counted
        # as a wrong guess against the newest code.
        resp = anon_client.post(reverse("verify_email"), {"code": old_code})
        assert User.objects.get(username="otp_user").is_active is False
        assert "Incorrect verification code" in resp.content.decode()

    def test_fresh_code_still_works(self, anon_client):
        do_signup(anon_client)
        first = latest_code_for("otp_user")

        EmailVerificationCode.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=5)
        )
        anon_client.post(reverse("resend_code"), follow=True)

        resp = anon_client.post(
            reverse("verify_email"), {"code": latest_code_for("otp_user").code}
        )
        assert resp["Location"] == reverse("profile")


# ---------------------------------------------------------------------------
# 7: rate limiting
# ---------------------------------------------------------------------------
class TestSendRateLimit:

    def test_resend_within_cooldown_is_blocked(self, anon_client):
        do_signup(anon_client)

        resp = anon_client.post(reverse("resend_code"), follow=True)

        assert resp.status_code == 200
        # Nothing new was delivered.
        assert len(mail.outbox) == 1
        assert any("wait" in str(m).lower() for m in resp.context["messages"])

    def test_resend_after_cooldown_is_allowed(self, anon_client):
        do_signup(anon_client)
        code = latest_code_for("otp_user")
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            created_at=timezone.now()
            - datetime.timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS + 5)
        )

        anon_client.post(reverse("resend_code"), follow=True)

        assert len(mail.outbox) == 2

    def test_daily_cap_blocks_further_sends(self, anon_client):
        """The cap is counted from the DB, not from client-side state."""
        do_signup(anon_client)
        code = latest_code_for("otp_user")

        # Backdate enough historical codes to sit at the cap.
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=2)
        )
        for _ in range(settings.EMAIL_VERIFICATION_DAILY_LIMIT):
            make_code(
                User.objects.get(username="otp_user"),
                created_at=timezone.now() - datetime.timedelta(minutes=5),
            )

        before = len(mail.outbox)
        anon_client.post(reverse("resend_code"), follow=True)

        assert len(mail.outbox) == before
        assert EmailVerificationCode.objects.filter(user__username="otp_user").count() == (
            settings.EMAIL_VERIFICATION_DAILY_LIMIT + 1
        )

    def test_service_raises_rate_limit(self, inactive_user):
        for _ in range(settings.EMAIL_VERIFICATION_DAILY_LIMIT):
            make_code(
                inactive_user,
                created_at=timezone.now() - datetime.timedelta(minutes=5),
            )

        with pytest.raises(VerificationRateLimit):
            generate_and_send_verification_code(inactive_user)


# ---------------------------------------------------------------------------
# Access control on the OTP page
# ---------------------------------------------------------------------------
class TestVerifyPageAccess:

    def test_anonymous_without_pending_signup_is_redirected(self, anon_client):
        resp = anon_client.get(reverse("verify_email"))

        assert resp.status_code == 302
        assert "auth" in resp["Location"]

    def test_authenticated_user_is_redirected_away(self, regular_client):
        resp = regular_client.get(reverse("verify_email"))

        assert resp.status_code == 302
        assert resp["Location"] == reverse("profile")

    def test_verified_user_cannot_reuse_the_page(self, anon_client):
        do_signup(anon_client)
        anon_client.post(
            reverse("verify_email"), {"code": latest_code_for("otp_user").code}
        )

        resp = anon_client.get(reverse("verify_email"))
        assert resp.status_code == 302
        assert resp["Location"] == reverse("profile")

    def test_expired_session_is_treated_as_no_pending_signup(
        self, anon_client, inactive_user
    ):
        """A pending verification older than the TTL must not be honoured."""
        session = anon_client.session
        session["verification_user_id"] = inactive_user.pk
        session["verification_started_at"] = (
            timezone.now().timestamp()
            - settings.EMAIL_VERIFICATION_SESSION_TTL_SECONDS
            - 60
        )
        session.save()

        resp = anon_client.get(reverse("verify_email"))

        assert resp.status_code == 302
        assert "auth" in resp["Location"]

    def test_fresh_session_is_accepted(self, anon_client, inactive_user):
        session = anon_client.session
        session["verification_user_id"] = inactive_user.pk
        session["verification_started_at"] = timezone.now().timestamp()
        session.save()

        resp = anon_client.get(reverse("verify_email"))

        assert resp.status_code == 200
        assert "o******r@example.com" in resp.content.decode()


# ---------------------------------------------------------------------------
# The resend countdown is server-owned, not a client-side guess
# ---------------------------------------------------------------------------
class TestResendCountdown:

    def test_countdown_is_full_just_after_a_send(self, anon_client):
        do_signup(anon_client)

        resp = anon_client.get(reverse("verify_email"))

        # Not an exact-equality check: the few ms between signup and this GET
        # would make a strict assertion flaky. The point is that the window is
        # (essentially) untouched, not that it is byte-identical.
        cooldown = settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
        assert cooldown - 2 <= resp.context["resend_in_seconds"] <= cooldown

    def test_countdown_is_partial_partway_through(self, anon_client):
        do_signup(anon_client)
        code = latest_code_for("otp_user")
        # The send happened 20s ago, so roughly 10s of the window remain.
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            created_at=timezone.now() - datetime.timedelta(seconds=20)
        )

        resp = anon_client.get(reverse("verify_email"))

        # Allow for the elapsed time between the backdate and the GET.
        assert 8 <= resp.context["resend_in_seconds"] <= 10

    def test_countdown_is_zero_once_elapsed(self, anon_client):
        """After the window the button must be usable, not stuck counting."""
        do_signup(anon_client)
        code = latest_code_for("otp_user")
        EmailVerificationCode.objects.filter(pk=code.pk).update(
            created_at=timezone.now()
            - datetime.timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS + 5)
        )

        resp = anon_client.get(reverse("verify_email"))

        assert resp.context["resend_in_seconds"] == 0

    def test_template_renders_the_server_value(self, anon_client):
        do_signup(anon_client)

        resp = anon_client.get(reverse("verify_email"))

        # Assert the template echoes whatever the view computed, rather than
        # hardcoding a number that drifts with test timing.
        expected = resp.context["resend_in_seconds"]
        assert f"var remaining = {expected};" in resp.content.decode()


# ---------------------------------------------------------------------------
# 8: transport failure must not break signup
# ---------------------------------------------------------------------------
class TestTransportFailure:

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_smtp_failure_does_not_500(self, monkeypatch):
        """Signup must survive the mail server being down."""
        from userapp.services import verification

        def boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(verification, "_deliver", boom)

        client = Client()
        resp = do_signup(client)

        # The account exists and the user is routed to the OTP page; they can
        # hit "Resend" once the mail server is back.
        assert resp.status_code == 302
        assert resp["Location"] == reverse("verify_email")
        assert User.objects.get(username="otp_user").is_active is False
        assert latest_code_for("otp_user") is not None

    def test_smtp_failure_is_logged(self, monkeypatch, caplog):
        import logging

        from userapp.services import verification

        def boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(verification, "_deliver", boom)

        with caplog.at_level(logging.ERROR, logger="userapp"):
            verification._deliver_or_log(
                User.objects.create_user(
                    username="mailfail", email="mailfail@example.com", password=PASSWORD
                ),
                "123456",
            )

        assert any("Failed to send verification code" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Service-level units
# ---------------------------------------------------------------------------
class TestServiceUnits:

    @pytest.mark.parametrize(
        ("email", "expected"),
        [
            ("otp_user@example.com", "o******r@example.com"),
            ("ab@example.com", "a*@example.com"),
            ("a@example.com", "a*@example.com"),
            ("", ""),
            (None, None),
            ("not-an-email", "not-an-email"),
        ],
    )
    def test_mask_email(self, email, expected):
        assert mask_email(email) == expected

    def test_code_is_uniformly_six_digits(self, inactive_user):
        codes = set()
        for _ in range(50):
            EmailVerificationCode.objects.filter(user=inactive_user).delete()
            # Bypass the send-rate policy: this loop exists to exercise the
            # generator, not the throttle (which has its own tests).
            obj = generate_and_send_verification_code(
                inactive_user, enforce_rate_limit=False
            )
            codes.add(obj.code)
            assert len(obj.code) == 6
            assert obj.code.isdigit()

        # A 6-digit space that only ever yields a handful of values would mean
        # the generator is broken; 50 draws over a 900k space is a cheap smoke
        # check, not a statistical proof.
        assert len(codes) > 20

    def test_verify_rejects_missing_code_row(self, inactive_user):
        success, message = verify_user_code(inactive_user, "123456")
        assert success is False
        assert "No verification code found" in message

    def test_verify_activates_user(self, inactive_user):
        obj = generate_and_send_verification_code(inactive_user)

        success, message = verify_user_code(inactive_user, obj.code)

        assert success is True
        inactive_user.refresh_from_db()
        assert inactive_user.is_active is True
        assert message == "Email verified successfully."

    def test_generating_a_second_code_invalidates_the_first(self, inactive_user):
        first = generate_and_send_verification_code(
            inactive_user, enforce_rate_limit=False
        )
        second = generate_and_send_verification_code(
            inactive_user, enforce_rate_limit=False
        )

        first.refresh_from_db()
        assert first.is_used is True
        assert second.is_used is False

    def test_generation_requires_an_email(self, make_user):
        # ``make_user`` backfills a blank email, so build the user directly.
        user = User.objects.create_user(
            username="noemail", email="", password=PASSWORD
        )
        with pytest.raises(Exception):
            generate_and_send_verification_code(user)


# ---------------------------------------------------------------------------
# The cleanup command
# ---------------------------------------------------------------------------
class TestCleanupCommand:

    def test_deletes_only_dead_codes_past_retention(self):
        from django.core.management import call_command

        user = User.objects.create_user(
            username="cleanup_user", email="cleanup@example.com", password=PASSWORD
        )
        old = timezone.now() - datetime.timedelta(days=60)
        recent = timezone.now() - datetime.timedelta(days=1)

        def mk(created, **kw):
            return make_code(user, created_at=created, **kw)

        dead_old = mk(old, is_used=True)
        expired_old = mk(old, expires_at=old - datetime.timedelta(minutes=1))
        live_old = mk(old)  # unspent and unexpired -> kept
        dead_recent = mk(recent, is_used=True)  # dead but inside retention

        call_command("cleanup_verification_codes", verbosity=0)

        remaining = set(
            EmailVerificationCode.objects.filter(user=user).values_list("pk", flat=True)
        )
        assert dead_old.pk not in remaining
        assert expired_old.pk not in remaining
        assert live_old.pk in remaining
        assert dead_recent.pk in remaining

    def test_dry_run_deletes_nothing(self):
        from django.core.management import call_command

        user = User.objects.create_user(
            username="dryrun_user", email="dryrun@example.com", password=PASSWORD
        )
        created = timezone.now() - datetime.timedelta(days=60)
        obj = make_code(
            user,
            created_at=created,
            expires_at=created + datetime.timedelta(minutes=15),
            is_used=True,
        )

        call_command("cleanup_verification_codes", "--dry-run", verbosity=0)

        assert EmailVerificationCode.objects.filter(pk=obj.pk).exists()
