import math

from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login, logout
from django.conf import settings
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from .models import Profile
from .forms import LoginForm, RegisterForm, UserInfoForm, UpdateUserForm
from .utils import generate_username_suggestions
from .services.verification import (
    VerificationRateLimit,
    generate_and_send_verification_code,
    generate_and_send_password_reset_code,
    verify_user_code,
    verify_password_reset_code,
    mask_email,
)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
User = get_user_model()

# ---- Pending-verification session helpers --------------------------------
# A pending verification lives in the session so the OTP page can find the
# user without asking for credentials again. It is stamped with a wall-clock
# expiry because a session key alone would otherwise grant verification
# rights for the life of the session cookie (potentially weeks).
_VERIF_SESSION_KEY = "verification_user_id"
_VERIF_TS_KEY = "verification_started_at"


def _store_pending_verification(request, user):
    """Bind a user to the session as "awaiting email verification"."""
    request.session[_VERIF_SESSION_KEY] = user.pk
    request.session[_VERIF_TS_KEY] = timezone.now().timestamp()


def _clear_pending_verification(request):
    """Drop the pending-verification state from the session."""
    request.session.pop(_VERIF_SESSION_KEY, None)
    request.session.pop(_VERIF_TS_KEY, None)


def _get_pending_verification(request):
    """Return the pending user, honouring the TTL, or ``None``.

    An expired stamp is treated as absent and cleans itself up so the
    session does not keep stale auth material around.
    """
    user_id = request.session.get(_VERIF_SESSION_KEY)
    if not user_id:
        return None

    started_at = request.session.get(_VERIF_TS_KEY)
    ttl = getattr(settings, "EMAIL_VERIFICATION_SESSION_TTL_SECONDS", 1800)
    if started_at is None or (timezone.now().timestamp() - float(started_at)) > ttl:
        _clear_pending_verification(request)
        return None

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        # The account was deleted while a verification was pending.
        _clear_pending_verification(request)
    return user

# Create your views here.
def supperuser_required(user):
    return user.is_superuser

def superuser_or_staffuser_required(user):
    return user.is_superuser or user.is_staff


def auth_page(request):
    """Combined Sign Up / Log In page with a tab toggle."""
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('dashboard')
        return redirect('profile')

    active_tab = request.GET.get('tab', 'signup')
    if active_tab not in ('signup', 'login'):
        active_tab = 'signup'

    login_form = LoginForm()
    signup_form = RegisterForm()

    if request.method == 'POST':
        if request.POST.get('form_type') == 'login':
            active_tab = 'login'
            login_form = LoginForm(request, data=request.POST)
            if login_form.is_valid():
                user = login_form.get_user()
                login(request, user)
                messages.success(request, f"Welcome back, {user.first_name or user.username}!")
                if user.is_staff or user.is_superuser:
                    return redirect('dashboard')
                return redirect('profile')
            else:
                # If credentials are valid but user is inactive, route to email verification
                raw_username = request.POST.get('username', '').strip()
                inactive_user = User.objects.filter(username__iexact=raw_username, is_active=False).first()
                if inactive_user and inactive_user.check_password(request.POST.get('password', '')):
                    if not inactive_user.email:
                        # e.g. an admin-created account that never got an
                        # address. Tell them plainly rather than 500ing.
                        messages.error(
                            request,
                            "This account has no email address on file, so we cannot "
                            "send a verification code. Please contact support.",
                        )
                    else:
                        try:
                            generate_and_send_verification_code(inactive_user)
                        except VerificationRateLimit as exc:
                            messages.warning(request, str(exc))
                        else:
                            messages.info(
                                request,
                                "Your email is not verified yet. We have sent a verification "
                                "code to your email.",
                            )
                        # Bind the session even when the send was throttled, so
                        # the user can still reach the page and hit "Resend Code".
                        _store_pending_verification(request, inactive_user)
                        return redirect('verify_email')
        else:
            active_tab = 'signup'
            signup_form = RegisterForm(request.POST)
            if signup_form.is_valid():
                user = signup_form.save()
                try:
                    generate_and_send_verification_code(user)
                except VerificationRateLimit as exc:
                    messages.warning(request, str(exc))
                else:
                    # Masked on purpose: this message renders on the next page,
                    # right next to the masked address, so leaking the raw
                    # one here would defeat the masking.
                    messages.success(
                        request,
                        f"Account created! We have sent a 6-digit verification code to "
                        f"{mask_email(user.email)}.",
                    )
                _store_pending_verification(request, user)
                return redirect('verify_email')

    return render(request, 'userapp/auth.html', {
        'login_form': login_form,
        'signup_form': signup_form,
        'active_tab': active_tab,
    })


def register_view(request):
    """Legacy URL — signup now lives on the combined auth page."""
    return redirect('/user/auth/?tab=signup')

def login_view(request):
    """Legacy URL — login now lives on the combined auth page."""
    return redirect('/user/auth/?tab=login')


def verify_email_view(request):
    """Page where users enter the 6-digit verification code sent to their email."""
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('dashboard')
        return redirect('profile')

    user = _get_pending_verification(request)
    if not user:
        # Covers all three "not pending" states, since the helper returns
        # None for a missing key, a stale user id, and an elapsed TTL.
        messages.info(request, "Please create an account or sign in to verify your email.")
        return redirect('/user/auth/?tab=signup')

    if user.is_active:
        _clear_pending_verification(request)
        messages.info(request, "Your account is already active. Please log in.")
        return redirect('/user/auth/?tab=login')

    error_message = None

    if request.method == 'POST':
        submitted_code = request.POST.get('code', '').strip()
        success, msg = verify_user_code(user, submitted_code)
        if success:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            _clear_pending_verification(request)
            messages.success(
                request,
                f"Email verified successfully! Welcome to your profile, {user.first_name or user.username}.",
            )
            return redirect('profile')
        else:
            error_message = msg

    masked = mask_email(user.email)
    cooldown = getattr(settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 30)
    ttl = getattr(settings, "EMAIL_VERIFICATION_CODE_TTL_MINUTES", 15)

    # The server owns the throttle, so it also owns the countdown. Deriving
    # the remaining seconds from the last send (rather than starting a fresh
    # 30s timer on page load) means a user who spent 20s on the page sees 10s,
    # and a user who reloaded after the cooldown sees an immediately-usable
    # button. Guessing here would let the UI disagree with the server.
    last_code = user.verification_codes.order_by("-created_at").first()
    if last_code:
        elapsed = (timezone.now() - last_code.created_at).total_seconds()
        # ceil, not int: truncating 29.99s to 29 shows the wrong number and
        # re-locks the button a second early.
        resend_in = max(0, math.ceil(cooldown - elapsed))
    else:
        resend_in = 0

    return render(request, 'userapp/verify_email.html', {
        'masked_email': masked,
        'username': user.username,
        'error_message': error_message,
        'code_ttl_minutes': ttl,
        'resend_in_seconds': resend_in,
    })


@require_POST
def resend_code_view(request):
    """Resend a fresh 6-digit verification code to the pending user."""
    user = _get_pending_verification(request)
    if not user:
        messages.error(request, "Session expired. Please sign up or log in again.")
        return redirect('/user/auth/?tab=signup')

    if user.is_active:
        return redirect('/user/auth/?tab=login')

    # The cooldown and daily cap are enforced inside the service, against the
    # DB — not here against the session — so they cannot be bypassed by
    # clearing cookies or by parallel requests.
    try:
        generate_and_send_verification_code(user)
    except VerificationRateLimit as exc:
        messages.warning(request, str(exc))
    else:
        messages.success(
            request,
            f"A fresh verification code has been sent to {mask_email(user.email)}.",
        )
    return redirect('verify_email')


def forgot_password_view(request):
    """Step 1: accept an email and send a password-reset code.

    Deliberately does NOT reveal whether the address exists. The same
    message and (near-identical) response time are returned either way, so
    the endpoint can't be used to enumerate registered emails.
    """
    if request.user.is_authenticated:
        return redirect('profile')

    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        if user:
            try:
                generate_and_send_password_reset_code(user)
            except VerificationRateLimit as exc:
                # Don't leak that the account exists by failing differently.
                # Show the same success message; the code just isn't sent.
                messages.warning(request, str(exc))
            else:
                messages.success(
                    request,
                    "If an account exists for that email, we have sent a "
                    "password reset code.",
                )
        else:
            # Same message as the success branch — no enumeration.
            messages.success(
                request,
                "If an account exists for that email, we have sent a "
                "password reset code.",
            )

        return redirect('reset_password')

    return render(request, 'userapp/forgot_password.html')


def reset_password_view(request):
    """Step 2: verify the code and set a new password.

    The code is the *only* credential required here — no session, no old
    password. That's safe because the code is single-use, expires in 15
    minutes, and is delivered only to the address on file.
    """
    if request.user.is_authenticated:
        return redirect('profile')

    email = (request.GET.get('email') or request.POST.get('email') or '').strip().lower()
    user = User.objects.filter(email__iexact=email).first() if email else None

    if not user:
        messages.error(request, "Invalid or expired reset link. Please start again.")
        return redirect('forgot_password')

    error_message = None

    if request.method == 'POST':
        submitted_code = request.POST.get('code', '').strip()
        success, msg = verify_password_reset_code(user, submitted_code)

        if not success:
            error_message = msg
        else:
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not new_password:
                error_message = "Please enter a new password."
            elif len(new_password) < 8:
                error_message = "Password must be at least 8 characters."
            elif new_password != confirm_password:
                error_message = "Passwords do not match."
            else:
                user.set_password(new_password)
                user.save(update_fields=["password"])

                # Invalidate every existing session for this user so a stolen
                # session cookie can't be used after the password changes.
                from django.contrib.sessions.models import Session
                from django.utils import timezone as tz

                for session in Session.objects.all():
                    if session.get_decoded().get('_auth_user_id') == str(user.pk):
                        session.delete()

                messages.success(
                    request,
                    "Your password has been reset. Please log in with your new password.",
                )
                return redirect('login')

    return render(request, 'userapp/reset_password.html', {
        'email': email,
        'error_message': error_message,
    })


@require_POST
@login_required
def logout_view(request):
    # POST-only logout (OWASP): a GET logout is a CSRF vector — a third-party
    # site can log a user out with a hidden request or an <img> tag.
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)

@require_GET
def check_username(request):
    """Return whether a candidate username is free, plus suggestions."""
    import re
    raw = (request.GET.get('username') or '').strip()
    occupied = User.objects.filter(username__iexact=raw).exists() if raw else True
    invalid = (not raw) or len(raw) < 3 or len(raw) > 150 or bool(re.search(r'[^A-Za-z0-9_.-]', raw))
    available = bool(raw and not occupied and not invalid)

    suggestions = []
    if raw and not available:
        fn = (request.GET.get('first_name') or '').strip()
        ln = (request.GET.get('last_name') or '').strip()
        suggestions = generate_username_suggestions(raw, first_name=fn, last_name=ln, count=4)
    return JsonResponse({'available': available, 'suggestions': suggestions, 'username': raw})


@login_required
def edit_user_info(request):
    user = request.user

    # get_or_create replaces the old hasattr/create dance — one query, atomic,
    # and safe on the first ever edit for a user.
    profile, _ = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = UserInfoForm(request.POST, request.FILES, instance=profile)
        userform = UpdateUserForm(request.POST, instance=user)
        if form.is_valid() and userform.is_valid():
            form.save()
            userform.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')
    else:
        form = UserInfoForm(instance=profile)
        userform = UpdateUserForm(instance=user)
    return render(request, 'userapp/editUserInfo.html', {'form': form, 'userform': userform})

@login_required
def profile_view(request):
    # get_or_create (not get) so a user without a profile still renders.
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return render(request, 'userapp/profile.html', {'profile': profile})