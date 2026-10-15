"""
Audit which accounts hold privileged flags (is_staff / is_superuser).

Usage:
    python manage.py audit_staff            # table of privileged accounts
    python manage.py audit_staff --demote   # strip flags from non-superusers

After the public `is_staff` signup escalation was removed (Phase 1), any
account that gained staff/superuser through that hole should be reviewed.
Superuser accounts are left alone by --demote; everything else is demoted.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "List (and optionally demote) accounts holding is_staff/is_superuser."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demote",
            action="store_true",
            help=(
                "Strip is_staff/is_superuser from every account that is NOT a "
                "superuser. Superuser accounts are never touched. Review the "
                "plain listing first before using this."
            ),
        )

    def handle(self, *args, **options):
        privileged = (
            User.objects.filter(models_q()).order_by("is_superuser", "username")
        )

        if not privileged.exists():
            self.stdout.write(self.style.SUCCESS("No privileged accounts. Clean."))
            return

        self.stdout.write(
            self.style.WARNING(f"{privileged.count()} privileged account(s):\n")
        )
        header = f"{'username':24} {'email':34} {'staff':6} {'super':6} {'last login':20}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for u in privileged:
            last = u.last_login.strftime("%Y-%m-%d %H:%M") if u.last_login else "never"
            self.stdout.write(
                f"{u.username[:23]:24} {(u.email or '-')[:33]:34} "
                f"{str(u.is_staff):6} {str(u.is_superuser):6} {last:20}"
            )

        if options["demote"]:
            self._demote()
        else:
            self.stdout.write(
                "\n"
                + self.style.NOTICE(
                    "Dry run. Re-run with --demote to strip staff/superuser "
                    "from every non-superuser account above."
                )
            )

    def _demote(self):
        victims = User.objects.filter(is_staff=True, is_superuser=False)
        count = victims.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to demote."))
            return
        for u in victims:
            u.is_staff = False
            u.save(update_fields=["is_staff"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Demoted {count} account(s): is_staff stripped. "
                "Superuser accounts were left untouched."
            )
        )


def models_q():
    """Q(is_staff=True) | Q(is_superuser=True) — kept as a helper for clarity."""
    from django.db.models import Q

    return Q(is_staff=True) | Q(is_superuser=True)
