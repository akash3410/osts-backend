"""Delete verification codes that can never be used again.

Codes are dead once they are spent, expired, or burned by too many wrong
guesses. Nothing in the request path ever deletes them, so this table grows
without bound and every signup writes another row. Run this daily:

    python manage.py cleanup_verification_codes            # 45-day retention
    python manage.py cleanup_verification_codes --days 7   # tighter window

Retention is deliberately longer than the 15-minute code lifetime: keeping
spent codes around for a while lets support answer "did this person ever
verify?" and lets us audit an account-takeover attempt after the fact.
"""
import os
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from userapp.models import EmailVerificationCode

DEFAULT_RETENTION_DAYS = 45


def _default_retention_days() -> int:
    """Retention from the environment, falling back to the default.

    Read here rather than at import time so a `--settings` override or a
    test's `override_settings` is honoured, and so a malformed value degrades
    to the default instead of crashing an unattended cron job.
    """
    raw = os.environ.get("VERIFICATION_CODE_RETENTION_DAYS", "")
    try:
        return int(raw) if raw else DEFAULT_RETENTION_DAYS
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def _dead_codes_queryset(cutoff):
    """Codes created before ``cutoff`` that can no longer be redeemed."""
    from django.conf import settings
    from django.db.models import Q

    max_attempts = getattr(settings, "EMAIL_VERIFICATION_MAX_ATTEMPTS", 5)
    return EmailVerificationCode.objects.filter(created_at__lt=cutoff).filter(
        Q(is_used=True)
        | Q(expires_at__lt=timezone.now())
        | Q(attempts__gte=max_attempts)
    )


class Command(BaseCommand):
    help = "Delete verification codes that are spent or expired, older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=(
                "Retention window in days "
                f"(default: $VERIFICATION_CODE_RETENTION_DAYS or {DEFAULT_RETENTION_DAYS})."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        retention_days = options["days"]
        if retention_days is None:
            retention_days = _default_retention_days()
        if retention_days < 0:
            raise CommandError("--days must be zero or positive.")
        dry_run = options["dry_run"]

        cutoff = timezone.now() - timedelta(days=retention_days)

        # A code is unrecoverable if it was spent, expired, or exhausted. All
        # three are gated on `created_at < cutoff` so a *live* code is never
        # swept, even if it was somehow flagged.
        dead = _dead_codes_queryset(cutoff)
        total = dead.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] Would delete {total} code(s) created before {cutoff:%Y-%m-%d %H:%M}."
                )
            )
            return

        deleted, _ = dead.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted} verification code(s) created before {cutoff:%Y-%m-%d %H:%M}."
            )
        )
