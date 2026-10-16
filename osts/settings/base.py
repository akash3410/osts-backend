"""
Base settings shared by every environment.

Everything here is environment-driven via django-environ. The concrete
environment (dev / prod) is selected in ``osts/settings/__init__.py``.
"""

from pathlib import Path
import os

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read .env from the project root (no-op if absent).
env = environ.Env()
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# ---- Core security -------------------------------------------------------
# In production this MUST come from the environment; the fallback only keeps
# ``runserver`` working locally.
SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-dev-only-do-not-use-in-production",
)

# DEBUG is decided per-environment; base default is False (safe by default).
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])


# ---- Application definition ---------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.humanize",
    # Local apps
    "myapp",
    "userapp",
    "dashboardapp",
    "core",
    "projects",
    "billing",
    # Third party
    "phonenumber_field",
    "axes",
    # django-allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.facebook",
    "allauth.socialaccount.providers.apple",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Axes (login throttling) — must come after AuthenticationMiddleware.
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
    # Axes credential-based lockout.
    "axes.backends.AxesStandaloneBackend",
]

SITE_ID = 1

ROOT_URLCONF = "osts.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_configuration",
                "core.context_processors.message_in_box",
            ],
        },
    },
]

WSGI_APPLICATION = "osts.wsgi.application"


# ---- Database ------------------------------------------------------------
# DATABASE_URL drives the engine. Empty/unset -> local SQLite so ``runserver``
# keeps working with zero setup; set DATABASE_URL to a postgres:// DSN in any
# environment that should use PostgreSQL ("PostgreSQL everywhere" in prod).
#
#   SQLite (dev default):  DATABASE_URL=   (empty or unset)
#   PostgreSQL:            postgres://user:pass@host:5432/dbname
#
# We resolve the raw string first (empty -> sqlite) and parse *that*, because
# env.db() would re-read the empty env var and ignore our default.
_database_url = env("DATABASE_URL", default="").strip()
if not _database_url:
    _database_url = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"

DATABASES = {"default": environ.Env.db_url_config(_database_url)}

if DATABASES["default"]["ENGINE"].endswith("postgresql"):
    DATABASES["default"].update(
        {
            # Reuse connections across requests instead of opening a new one
            # per request — cheaper and avoids connection storms.
            "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=60),
            # Django 5.1+: drop connections that look dead (e.g. after a
            # DB restart / pooler recycle) before handing them to a view.
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "connect_timeout": env.int("DB_CONNECT_TIMEOUT", default=5),
            },
        }
    )


# ---- Password validation -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---- Internationalization ------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True


# ---- Static files (CSS, JavaScript, Images) ------------------------------
STATIC_URL = "static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", str(BASE_DIR / "staticfiles"))

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---- Auth / allauth ------------------------------------------------------
# Custom user model. This MUST be set before the first migration that creates
# any FK to the user table, and Django cannot change it once other apps
# reference it — so it lands early, by design.
AUTH_USER_MODEL = "userapp.User"

LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/user/profile/"
LOGOUT_REDIRECT_URL = "/"

# NOTE: allauth (>= 65) reads social app credentials from the database
# (SocialApp model), not from settings. Seed them from env vars with:
#   GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
#   python manage.py seed_social_apps
ACCOUNT_LOGIN_METHODS = {"username"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_UNIQUE_EMAIL = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
    "facebook": {
        "SCOPE": ["email", "public_profile"],
        "AUTH_PARAMS": {"auth_type": "reauthenticate"},
        "METHOD": "oauth2",
        "VERIFIED_EMAIL": True,
    },
    "apple": {},
}

# ---- Media ---------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", os.path.join(BASE_DIR, "media"))


# ---- Email ---------------------------------------------------------------
# Console backend by default so nothing silently tries to hit a real SMTP
# server in development. Override in prod.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@osts.local")


# ---- Cache (Redis when configured, else local memory) --------------------
# Phase 2+ leans on this heavily; wiring it now keeps the interface stable.
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "osts-dev-cache",
        }
    }

# Sessions: DB-backed (works everywhere), swapped to Redis cache later if
# REDIS_URL is provided by simply changing this line in prod.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"


# ---- django-axes (login throttling) --------------------------------------
from datetime import timedelta  # noqa: E402

AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
# Lock a credential out for 15 minutes after the failure limit is hit.
AXES_COOLOFF_TIME = timedelta(minutes=env.int("AXES_COOLOFF_MINUTES", default=15))
# Count failures per (username, IP) pair so one attacker can't lock out a
# legit user from a shared NAT, and one user can't lock out the whole office.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
# A successful login clears that credential's failure counter.
AXES_RESET_ON_SUCCESS = True
