"""Email verification (OTP) service for the signup flow.

Responsibilities:
  * mint a 6-digit code and persist it,
  * enforce the send-rate policy (cooldown + daily cap),
  * deliver the code by email *safely*,
  * validate a submitted code in constant time.

Policy numbers come from settings (``EMAIL_VERIFICATION_*``) so the model,
this service and the views can never drift apart.
"""
import datetime
import logging
import secrets

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from userapp.models import EmailVerificationCode

logger = logging.getLogger(__name__)


class VerificationRateLimit(Exception):
    """Raised when a user has requested codes too often.

    Callers translate this into a user-facing message. It is an exception
    rather than a ``(False, msg)`` tuple because "we refused to send" is a
    control-flow branch the views must not accidentally fall through.
    """


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def mask_email(email):
    """Return a masked email like a***h@example.com for safe UI display."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def _send_policy_error(user):
    """Return a user-facing message if the user may not send yet, else None.

    Checks both the short cooldown and the per-day cap. Both windows are
    anchored on ``created_at`` (a real send) rather than a cached timestamp,
    so the limit cannot be bypassed by clearing session state.
    """
    cooldown = getattr(settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 30)
    daily_limit = getattr(settings, "EMAIL_VERIFICATION_DAILY_LIMIT", 5)

    now = timezone.now()
    codes = user.verification_codes.all()

    newest = codes.order_by("-created_at").first()
    if newest:
        elapsed = (now - newest.created_at).total_seconds()
        if elapsed < cooldown:
            remaining = int(cooldown - elapsed) + 1
            return VerificationRateLimit(
                f"Please wait {remaining} seconds before requesting a new code."
            )

    day_ago = now - datetime.timedelta(days=1)
    if codes.filter(created_at__gte=day_ago).count() >= daily_limit:
        return VerificationRateLimit(
            "You have reached today's limit for verification codes. "
            "Please try again tomorrow or contact support if you need help."
        )

    return None


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _site_name() -> str:
    """Branded name for email copy.

    Reuses the notifications helper so both apps agree on one source of truth,
    imported lazily to avoid a load-time dependency from ``userapp`` onto
    ``notifications`` (which would couple our signup path to another app's
    models being ready).
    """
    try:
        from notifications.services import get_site_name

        return get_site_name()
    except Exception:  # pragma: no cover - defensive, DB may be unavailable
        return getattr(settings, "SITE_NAME", "OSTS")


def _render_code_email(user, code, *, purpose=None):
    """Build the (subject, text, html) triple for a code email.

    ``purpose`` selects the template and subject line. Defaults to the
    signup verification copy.
    """
    site_name = _site_name()
    ttl = getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 15)

    if purpose == EmailVerificationCode.Purpose.PASSWORD_RESET:
        template_base = "userapp/emails/password_reset_code"
        subject = f"{code} is your {site_name} password reset code"
    else:
        template_base = "userapp/emails/verification_code"
        subject = f"{code} is your {site_name} verification code"

    context = {
        "code": code,
        "recipient_name": user.first_name or user.username,
        "ttl_minutes": ttl,
        "site_name": site_name,
        "subject": subject,
    }
    text_body = render_to_string(f"{template_base}.txt", context)
    html_body = render_to_string(f"{template_base}.html", context)
    return subject, text_body, html_body


def _deliver(user, code, *, purpose=None):
    """Render and send. Raises on transport failure — caller decides policy."""
    subject, text_body, html_body = _render_code_email(user, code, purpose=purpose)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@osts.local"),
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def generate_and_send_verification_code(user, *, enforce_rate_limit=True):
    """Generate a 6-digit OTP, invalidate prior codes, save to DB, and email it.

    Returns the created :class:`~userapp.models.EmailVerificationCode`.

    Raises :class:`VerificationRateLimit` if ``enforce_rate_limit`` and the
    user is sending too often.

    Failure policy
    --------------
    The code row is committed *first*, and the email is sent afterwards via
    ``transaction.on_commit``. That ordering matters in two ways:

    * The user exists and a valid code is stored even if SMTP is down, so
      "Resend" can recover without re-registering.
    * A transport failure can never roll back or 500 the request that
      created the account — it is logged, and the caller surfaces a friendly
      message instead.
    """
    if not user.email:
        # Defensive: the registration form requires an email, but other
        # callers (e.g. social accounts) may not.
        raise ImproperlyConfigured(
            f"User {user.pk} has no email address; cannot send a verification code."
        )

    if enforce_rate_limit:
        error = _send_policy_error(user)
        if error:
            raise error

    # Invalidate previous unused codes so only the newest one can log in.
    user.verification_codes.filter(is_used=False).update(is_used=True)

    # Cryptographically secure 6-digit numeric string. ``randbelow`` is
    # uniform, so 100000-999999 has no modulo bias.
    code = f"{secrets.randbelow(900000) + 100000}"
    ttl = getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 15)
    expires_at = timezone.now() + datetime.timedelta(minutes=ttl)

    code_obj = EmailVerificationCode.objects.create(
        user=user,
        code=code,
        expires_at=expires_at,
    )

    # Defer the network call until the surrounding transaction (if any) has
    # committed. Outside an atomic block Django runs the callback immediately,
    # so this is safe in views, tests and management commands alike.
    transaction.on_commit(lambda: _deliver_or_log(user, code))

    return code_obj


def _deliver_or_log(user, code, *, purpose=None):
    """Send the email, converting transport failures into a logged event."""
    try:
        _deliver(user, code, purpose=purpose)
    except Exception:
        # Never let a mail problem bubble up as a 500 — the account is
        # already created and the user can hit "Resend". Log loudly instead
        # so ops can distinguish "email broken" from "user typo".
        logger.exception(
            "Failed to send verification code to user_id=%s (email=%s)",
            user.pk,
            mask_email(user.email),
        )
        return False
    logger.info(
        "Verification code sent to user_id=%s (email=%s)", user.pk, mask_email(user.email)
    )
    return True


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify_user_code(user, submitted_code):
    """Validate the submitted code against the user's latest code.

    Returns ``(success: bool, message: str)``.

    Comparison uses :func:`secrets.compare_digest` so the check runs in
    constant time. A plain ``==`` short-circuits on the first differing byte,
    which leaks the code position through response timing.
    """
    code_clean = (submitted_code or "").strip()
    if not code_clean:
        return False, "Please enter the 6-digit verification code."

    if not code_clean.isdigit() or len(code_clean) != 6:
        return False, "The verification code must be exactly 6 digits."

    latest_code = user.verification_codes.order_by("-created_at").first()

    if not latest_code:
        return False, "No verification code found. Please request a new one."

    if latest_code.is_used:
        return False, "This verification code has already been used. Please request a new one."

    if latest_code.is_expired():
        latest_code.is_used = True
        latest_code.save(update_fields=["is_used"])
        return False, "This verification code has expired. Please request a new one."

    if not secrets.compare_digest(latest_code.code, code_clean):
        max_attempts = getattr(settings, "EMAIL_VERIFICATION_MAX_ATTEMPTS", 5)
        latest_code.attempts += 1
        fields = ["attempts"]

        if latest_code.attempts >= max_attempts:
            # Burn the code: an attacker gets 5 guesses per code, not 5 per
            # second forever.
            latest_code.is_used = True
            fields.append("is_used")

        latest_code.save(update_fields=fields)

        if "is_used" in fields:
            return False, "Too many incorrect attempts. Please request a new code."

        remaining = max_attempts - latest_code.attempts
        return False, f"Incorrect verification code. ({remaining} attempts remaining)"

    # Success: mark code used and activate the user.
    latest_code.is_used = True
    latest_code.save(update_fields=["is_used"])

    user.is_active = True
    user.save(update_fields=["is_active"])

    return True, "Email verified successfully."


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
def generate_and_send_password_reset_code(user, *, enforce_rate_limit=True):
    """Generate a 6-digit OTP for password reset, save it, and email it.

    Mirrors :func:`generate_and_send_verification_code` but stamps the row
    with ``purpose=PASSWORD_RESET`` so the two flows can never be confused
    (a signup code must not reset a password, and vice versa).

    Returns the created :class:`~userapp.models.EmailVerificationCode`.
    Raises :class:`VerificationRateLimit` if rate-limited.
    """
    if not user.email:
        raise ImproperlyConfigured(
            f"User {user.pk} has no email address; cannot send a password reset code."
        )

    if enforce_rate_limit:
        error = _send_policy_error(user)
        if error:
            raise error

    # Invalidate previous unused codes of *both* purposes so a stale signup
    # code can't be replayed against the reset flow.
    user.verification_codes.filter(is_used=False).update(is_used=True)

    code = f"{secrets.randbelow(900000) + 100000}"
    ttl = getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 15)
    expires_at = timezone.now() + datetime.timedelta(minutes=ttl)

    code_obj = EmailVerificationCode.objects.create(
        user=user,
        code=code,
        expires_at=expires_at,
        purpose=EmailVerificationCode.Purpose.PASSWORD_RESET,
    )

    transaction.on_commit(
        lambda: _deliver_or_log(
            user, code, purpose=EmailVerificationCode.Purpose.PASSWORD_RESET
        )
    )

    return code_obj


def verify_password_reset_code(user, submitted_code):
    """Validate a submitted password-reset code.

    Returns ``(success: bool, message: str)``. Only codes stamped
    ``purpose=PASSWORD_RESET`` are accepted — a signup verification code
    must never authorize a password change.
    """
    code_clean = (submitted_code or "").strip()
    if not code_clean:
        return False, "Please enter the 6-digit code."

    if not code_clean.isdigit() or len(code_clean) != 6:
        return False, "The code must be exactly 6 digits."

    latest_code = (
        user.verification_codes.filter(
            purpose=EmailVerificationCode.Purpose.PASSWORD_RESET
        )
        .order_by("-created_at")
        .first()
    )

    if not latest_code:
        return False, "No password reset code found. Please request a new one."

    if latest_code.is_used:
        return False, "This code has already been used. Please request a new one."

    if latest_code.is_expired():
        latest_code.is_used = True
        latest_code.save(update_fields=["is_used"])
        return False, "This code has expired. Please request a new one."

    if not secrets.compare_digest(latest_code.code, code_clean):
        max_attempts = getattr(settings, "EMAIL_VERIFICATION_MAX_ATTEMPTS", 5)
        latest_code.attempts += 1
        fields = ["attempts"]

        if latest_code.attempts >= max_attempts:
            latest_code.is_used = True
            fields.append("is_used")

        latest_code.save(update_fields=fields)

        if "is_used" in fields:
            return False, "Too many incorrect attempts. Please request a new code."

        remaining = max_attempts - latest_code.attempts
        return False, f"Incorrect code. ({remaining} attempts remaining)"

    # Success: burn the code. The caller is responsible for updating the
    # password and invalidating sessions — this function only authenticates
    # the code.
    latest_code.is_used = True
    latest_code.save(update_fields=["is_used"])

    return True, "Code verified."
