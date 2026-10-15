"""Base manager patterns for the service layer.

apps add domain-specific managers on top. The rule of thumb in this codebase:

* Plain app-level business queries (e.g. "open inquiries") live in
  managers.py as QuerySet methods — they're reusable by views, admin, tests and
  (later) DRF serializers without being tied to the HTTP request.
* Business logic that mutates state (status transitions, number allocation,
  sending email) lives in services.py — functions that accept the needed
  inputs and return plain models. Views stay thin: validate input via a form,
  call the service, redirect/render.

No DRF here (Phase 5 prep). The signatures are written so that exposing them
via serializers later is trivial.
"""
from django.db import models


class BaseManager(models.Manager):
    """Convenience base for all managers in this project."""

    def get_queryset(self):
        return super().get_queryset()


class TimestampedManager(models.Manager):
    """Manager that defaults to newest-first ordering for timestamped models."""

    def get_queryset(self):
        return super().get_queryset().order_by('-created_at')