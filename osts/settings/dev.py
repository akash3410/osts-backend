"""Development settings — local SQLite, verbose error pages, debug tooling."""

from .base import *  # noqa: F401,F403
from .base import env

# DEBUG defaults to True locally unless .env says otherwise.
DEBUG = env.bool("DEBUG", default=True)

# Localhost by default. "testserver" is the host Django's test Client sends,
# so tests work out of the box.
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]", "testserver"]
)

# Whitenoise serves static files straight off the app in dev too — no need to
# run a separate static server.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# django-debug-toolbar is optional — only wired if installed.
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass

# nplusone surfaces accidental N+1 queries loudly during development.
try:
    import nplusone  # noqa: F401

    INSTALLED_APPS += ["nplusone.ext.django"]  # noqa: F405
    MIDDLEWARE.insert(2, "nplusone.ext.django.NPlusOneMiddleware")  # noqa: F405
except ImportError:
    pass
