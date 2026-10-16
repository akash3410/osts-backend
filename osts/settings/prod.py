"""Production settings — hardened security, HTTPS-only, static via WhiteNoise.

Every value here is the safe default; nothing depends on a developer machine.
``manage.py check --deploy`` is expected to be clean with this module.
"""

from .base import *  # noqa: F401,F403
from .base import env

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

DEBUG = False

# In production both of these MUST be supplied by the environment. We refuse
# to boot with a missing SECRET_KEY rather than fall back to the dev default.
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---- Static / media storage ---------------------------------------------
# WhiteNoise serves hashed, compressed static files with far-future cache
# headers. Manifest storage makes the hashed filenames mandatory, so a stale
# reference fails loudly instead of silently 404ing in a user's browser.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---- Transport security --------------------------------------------------
# Redirect every non-HTTPS request to HTTPS.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Tell Django it's behind HTTPS (sets request.is_secure(), correct redirects).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS: once a browser has talked HTTPS to us, force it for a year on this
# host (including subdomains). Start low, raise after verifying HTTPS works.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

# ---- Cookies -------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---- Clickjacking / content sniffing ------------------------------------
X_FRAME_OPTIONS = "DENY"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# ---- Email ---------------------------------------------------------------
# SMTP transport is read in base.py so dev and prod share one definition.
# Here we only add the production guards: an unconfigured console backend
# silently "succeeds", so every verification code would be printed to the
# container log and no user would ever receive one. We refuse to boot instead.
EMAIL_BACKEND = env("EMAIL_BACKEND")
if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
    raise ImproperlyConfigured(
        "EMAIL_BACKEND is the console backend in production. Set "
        "EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend (or a "
        "transactional provider's backend) in your environment."
    )

# The SMTP backend is unusable without a host; third-party provider backends
# (AmazonsES, SendGrid, Postmark...) carry their own credentials, so we only
# enforce the host when SMTP is actually selected.
if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not EMAIL_HOST:
    raise ImproperlyConfigured(
        "EMAIL_BACKEND is smtp but EMAIL_HOST is empty. Set EMAIL_HOST "
        "(e.g. smtp.sendgrid.net) or switch to a provider backend."
    )

# ---- Passwords -----------------------------------------------------------
# PBKDF2 is Django's default; scrypt is stronger and available on this box.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

# ---- Logging -------------------------------------------------------------
# Console output (captured by Docker / journald). ERROR+ goes to stderr.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("ROOT_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        # Loud on purpose: auth failures and payment flows are auditable.
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Verification email delivery failures are security-relevant: they
        # mean a user is stuck with an inactive account and no code.
        "userapp": {
            "handlers": ["console"],
            "level": env("USERAPP_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
    },
}
