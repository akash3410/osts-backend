"""Notifications domain: outbox email notifications tied to billing/project events.

Notifications are an outbox — rows are created for every event that needs to
reach a user, then dispatched by a management command. Each notification is
created exactly once per (user, template, related_object) to avoid spam, and
the command marks rows sent/failed so nothing is lost.
"""

from django.db import models
from django.utils import timezone

from userapp.models import User


class NotificationTemplate(models.TextChoices):
    INVOICE_SENT = "invoice_sent", "Invoice sent"
    INVOICE_PAID = "invoice_paid", "Invoice paid"
    INVOICE_OVERDUE = "invoice_overdue", "Invoice overdue"
    PAYMENT_RECEIVED = "payment_received", "Payment received"
    PAYMENT_VOIDED = "payment_voided", "Payment voided"
    PROJECT_ASSIGNED = "project_assigned", "Project assigned"
    TASK_ASSIGNED = "task_assigned", "Task assigned"
    TASK_DUE_SOON = "task_due_soon", "Task due soon"
    MILESTONE_COMPLETED = "milestone_completed", "Milestone completed"
    GENERIC = "generic", "Generic"


class Notification(models.Model):
    """Single outbox notification row. Dispatch once per (user, template, ref)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    template = models.CharField(max_length=30, choices=NotificationTemplate.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)

    # Generic relation to the triggering object (invoice/payment/project/task).
    related_app = models.CharField(max_length=30, blank=True)
    related_model = models.CharField(max_length=30, blank=True)
    related_pk = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "email_sent", "created_at"]),
            models.Index(fields=["template", "related_app", "related_model", "related_pk"]),
        ]

    def __str__(self):
        return f"{self.template} -> {self.user.username} ({self.title})"


class NotificationPreference(models.Model):
    """Per-user notification toggle. Defaults to on for every template."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    invoice_sent = models.BooleanField(default=True)
    invoice_paid = models.BooleanField(default=True)
    invoice_overdue = models.BooleanField(default=True)
    payment_received = models.BooleanField(default=True)
    payment_voided = models.BooleanField(default=True)
    project_assigned = models.BooleanField(default=True)
    task_assigned = models.BooleanField(default=True)
    task_due_soon = models.BooleanField(default=True)
    milestone_completed = models.BooleanField(default=True)
    marketing = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"prefs:{self.user.username}"

    def template_enabled(self, template: NotificationTemplate) -> bool:
        mapping = {
            NotificationTemplate.INVOICE_SENT: self.invoice_sent,
            NotificationTemplate.INVOICE_PAID: self.invoice_paid,
            NotificationTemplate.INVOICE_OVERDUE: self.invoice_overdue,
            NotificationTemplate.PAYMENT_RECEIVED: self.payment_received,
            NotificationTemplate.PAYMENT_VOIDED: self.payment_voided,
            NotificationTemplate.PROJECT_ASSIGNED: self.project_assigned,
            NotificationTemplate.TASK_ASSIGNED: self.task_assigned,
            NotificationTemplate.TASK_DUE_SOON: self.task_due_soon,
            NotificationTemplate.MILESTONE_COMPLETED: self.milestone_completed,
        }
        return mapping.get(template, True)
