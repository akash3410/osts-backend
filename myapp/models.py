from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from core.models import TimeStampedModel
from dashboardapp.models import Service


class Inquiry(TimeStampedModel):
    """A public contact/quote request (formerly ``Messages``).

    Renamed + refactored in Phase 3:
      * ``service`` was a free-text CharField -> now a real FK to Service, with
        ``service_title`` snapshotting the title at submission time so the
        inquiry still reads correctly if the Service is later renamed/deleted.
      * ``response`` (bool) -> ``status`` choices, so the pipeline can track
        New -> In progress -> Replied -> Closed instead of a single flag.
      * ``response_at`` (auto_now — it bumped on EVERY save, the Phase-1 bug)
        -> ``responded_at``, set explicitly only when the status moves to a
        "responded" state.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        REPLIED = "replied", "Replied"
        CLOSED = "closed", "Closed"

    #: Statuses that still need attention (shown in the dashboard inbox badge).
    OPEN_STATUSES = (Status.NEW, Status.IN_PROGRESS)
    #: Statuses that count as "we got back to them".
    RESPONDED_STATUSES = (Status.REPLIED, Status.CLOSED)

    name = models.CharField(max_length=70)
    email = models.EmailField()
    phone = PhoneNumberField(region="BD", null=True, blank=True)

    service = models.ForeignKey(
        Service,
        on_delete=models.SET_NULL,  # keep the inquiry even if the service goes
        null=True,
        blank=True,
        related_name="inquiries",
    )
    # Snapshot of the service title at submission time (and a fallback for
    # inquiries whose service row was deleted).
    service_title = models.CharField(max_length=255, blank=True, default="")

    note = models.TextField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    # Only set when the status enters a "responded" state (NOT auto_now).
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        verbose_name_plural = "inquiries"
        # The inbox is the hottest read: open ones, newest first. A partial
        # index keeps it tiny (only unclosed rows are indexed).
        indexes = [
            models.Index(
                fields=["-created_at"],
                condition=models.Q(status__in=("new", "in_progress")),
                name="inquiry_open_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} — {self.service_title or self.get_status_display()}"

    # ------------------------------------------------------------------
    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def save(self, *args, **kwargs):
        # Keep the service_title snapshot in sync while a service is attached.
        if self.service_id:
            self.service_title = self.service.title
        # Maintain responded_at: stamp it when moving into a responded status,
        # clear it if the inquiry is reopened.
        if self.status in self.RESPONDED_STATUSES:
            if self.responded_at is None:
                from django.utils import timezone

                self.responded_at = timezone.now()
        else:
            self.responded_at = None
        super().save(*args, **kwargs)
