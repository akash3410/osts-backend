"""Notification service layer.

Central place to create outbox notification rows when business events happen
(invoice sent/paid/overdue, payment received/voided, project/task milestones).

Views call these functions so notification logic stays consistent across web
and future API.
"""
from decimal import Decimal

from django.contrib.sites.models import Site
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from notifications.models import Notification, NotificationPreference, NotificationTemplate


def get_site_name() -> str:
    try:
        return Site.objects.get_current().name
    except Exception:
        return "OSTS"


def _get_prefs(user) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs


def _should_create(user, template) -> bool:
    prefs = _get_prefs(user)
    return prefs.template_enabled(template)


def _already_sent(user, template, related_app, related_model, related_pk) -> bool:
    return Notification.objects.filter(
        user=user,
        template=template,
        related_app=related_app,
        related_model=related_model,
        related_pk=related_pk,
    ).exists()


def notify(
    user,
    template,
    *,
    title: str,
    body: str = "",
    related_app: str = "",
    related_model: str = "",
    related_pk=None,
    force: bool = False,
):
    """Create a notification row if not already sent for this object.

    Idempotent by (user, template, related_*). Re-creating for the same
    object does nothing unless force=True.
    """
    if user is None or not user.pk:
        return None
    if not _should_create(user, template) and not force:
        return None
    if not force and related_app and related_model and related_pk is not None:
        if _already_sent(user, template, related_app, related_model, related_pk):
            return None

    notif = Notification.objects.create(
        user=user,
        template=template,
        title=title,
        body=body,
        related_app=related_app,
        related_model=related_model,
        related_pk=related_pk,
    )
    return notif


# ---------------------------------------------------------------------------
# Billing event helpers
# ---------------------------------------------------------------------------
def invoice_sent(invoice):
    """Called when an invoice is marked sent."""
    user = invoice.client.user
    title = f"Invoice {invoice.number} sent"
    body = render_to_string(
        "notifications/email/invoice_sent.txt",
        {
            "invoice": invoice,
            "site_name": get_site_name(),
            "total": invoice.total,
            "due_date": invoice.due_date,
        },
    )
    return notify(
        user,
        NotificationTemplate.INVOICE_SENT,
        title=title,
        body=body,
        related_app="billing",
        related_model="invoice",
        related_pk=invoice.pk,
    )


def payment_received(payment):
    """Called when a payment lands on an invoice."""
    user = payment.client.user
    title = f"Payment {payment.number} received"
    body = render_to_string(
        "notifications/email/payment_received.txt",
        {
            "payment": payment,
            "invoice": payment.invoice,
            "site_name": get_site_name(),
            "amount": payment.amount,
        },
    )
    return notify(
        user,
        NotificationTemplate.PAYMENT_RECEIVED,
        title=title,
        body=body,
        related_app="billing",
        related_model="payment",
        related_pk=payment.pk,
    )


def invoice_overdue(invoice):
    """Called when an invoice passes its due date unpaid."""
    user = invoice.client.user
    title = f"Invoice {invoice.number} is overdue"
    body = render_to_string(
        "notifications/email/invoice_overdue.txt",
        {
            "invoice": invoice,
            "site_name": get_site_name(),
            "balance_due": invoice.balance_due,
            "due_date": invoice.due_date,
        },
    )
    return notify(
        user,
        NotificationTemplate.INVOICE_OVERDUE,
        title=title,
        body=body,
        related_app="billing",
        related_model="invoice",
        related_pk=invoice.pk,
    )


def invoice_overdue(invoice):
    """Called when an invoice passes its due date unpaid."""
    user = invoice.client.user
    title = f"Invoice {invoice.number} is overdue"
    body = render_to_string(
        "notifications/email/invoice_overdue.txt",
        {
            "invoice": invoice,
            "site_name": get_site_name(),
            "balance_due": invoice.balance_due,
            "due_date": invoice.due_date,
        },
    )
    return notify(
        user,
        NotificationTemplate.INVOICE_OVERDUE,
        title=title,
        body=body,
        related_app="billing",
        related_model="invoice",
        related_pk=invoice.pk,
    )


# ---------------------------------------------------------------------------
# Project / task helpers
# ---------------------------------------------------------------------------
def project_assigned(project, assigned_to):
    user = assigned_to
    title = f"You were added to project '{project.name}'"
    body = render_to_string(
        "notifications/email/project_assigned.txt",
        {
            "project": project,
            "site_name": get_site_name(),
        },
    )
    return notify(
        user,
        NotificationTemplate.PROJECT_ASSIGNED,
        title=title,
        body=body,
        related_app="projects",
        related_model="project",
        related_pk=project.pk,
    )


def task_assigned(task):
    user = task.assignee
    title = f"Task '{task.title}' assigned to you"
    body = render_to_string(
        "notifications/email/task_assigned.txt",
        {
            "task": task,
            "milestone": task.milestone,
            "site_name": get_site_name(),
        },
    )
    return notify(
        user,
        NotificationTemplate.TASK_ASSIGNED,
        title=title,
        body=body,
        related_app="projects",
        related_model="task",
        related_pk=task.pk,
    )


# ---------------------------------------------------------------------------
# Generic helper for views that want to fire a one-off notification
# ---------------------------------------------------------------------------
def send_notification(
    user,
    template,
    title: str,
    body: str = "",
    related_app: str = "",
    related_model: str = "",
    related_pk=None,
    force: bool = False,
):
    """Public wrapper so views don't import internals."""
    return notify(
        user,
        template,
        title=title,
        body=body,
        related_app=related_app,
        related_model=related_model,
        related_pk=related_pk,
        force=force,
    )
