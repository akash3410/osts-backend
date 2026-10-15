"""
Settings package entry point.

``DJANGO_SETTINGS_MODULE='osts.settings'`` stays valid for manage.py, wsgi.py
and asgi.py. The concrete environment is chosen by the ``OSTS_ENV`` variable:

    OSTS_ENV=dev   (default)  -> osts.settings.dev
    OSTS_ENV=prod             -> osts.settings.prod

Set OSTS_ENV=prod in the production container / process manager.
"""

import os

_env = os.environ.get("OSTS_ENV", "dev").strip().lower()

if _env == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
