"""Dispatch pending outbox notifications via email.

Usage:
    python manage.py notify_dispatch                 # send all unsent
    python manage.py notify_dispatch --template invoice_sent   # only one template
    python manage.py notify_dispatch --user 5         # only one user
    python manage.py notify_dispatch --dry-run        # report only

Each notification is sent once and marked email_sent=True on success.
Failures are recorded in email_error and retried on the next run.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import Notification, NotificationTemplate

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send pending outbox notifications via email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--template",
            choices=[t[0] for t in NotificationTemplate.choices],
            help="Only dispatch this template.",
        )
        parser.add_argument(
            "--user", type=int, help="Only dispatch notifications for this user id."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without writing anything.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        qs = Notification.objects.filter(email_sent=False)

        template = options.get("template")
        if template:
            qs = qs.filter(template=template)

        user_id = options.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        qs = qs.select_related("user").order_by("created_at")

        if dry:
            self.stdout.write(f"Dry run — {qs.count()} notifications would be sent:")
            for n in qs:
                self.stdout.write(f"  {n.pk} {n.template} -> {n.user.username}: {n.title}")
            return

        sent = 0
        failed = 0
        for n in qs:
            ok = self._send_one(n)
            if ok:
                n.email_sent = True
                n.email_sent_at = timezone.now()
                n.email_error = ""
                n.save(update_fields=["email_sent", "email_sent_at", "email_error"])
                sent += 1
                logger.info("notification %d sent to %s", n.pk, n.user.username)
            else:
                failed += 1
                logger.warning("notification %d failed for %s: %s", n.pk, n.user.username, n.email_error)

        self.stdout.write(
            self.style.SUCCESS(f"Sent {sent}, failed {failed}, total {qs.count()}")
        )

    def _send_one(self, n: Notification) -> bool:
        from_user = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")
        try:
            email = EmailMessage(
                subject=n.title,
                body=n.body,
                from_email=from_user,
                to=[n.user.email],
            )
            email.send(fail_silently=False)
            return True
        except Exception as exc:  # noqa: BLE001
            n.email_error = str(exc)[:500]
            n.save(update_fields=["email_error"])
            return False
