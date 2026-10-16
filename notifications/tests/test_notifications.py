"""Tests for the notifications domain (Phase 9)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from userapp.models import Client
from billing.models import Invoice, InvoiceLine, Payment
from billing.services import apply_payment_to_invoice, finalize_invoice, initiate_payment
from notifications.models import Notification, NotificationPreference
from notifications.services import invoice_sent, payment_received, invoice_overdue, notify

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
class TestNotificationPreference:
    def test_template_defaults_on(self, make_user):
        u = make_user("prefuser")
        prefs, _ = NotificationPreference.objects.get_or_create(user=u)
        assert prefs.template_enabled("invoice_sent") is True
        assert prefs.template_enabled("invoice_paid") is True
        prefs.invoice_sent = False
        prefs.save()
        assert prefs.template_enabled("invoice_sent") is False

    def test_invoice_disabled_skips_notify(self, make_user):
        u = make_user("nouser")
        prefs = NotificationPreference.objects.create(user=u, invoice_sent=False)
        result = notify(u, "invoice_sent", title="t", body="b")
        assert result is None
        assert Notification.objects.count() == 0


# ---------------------------------------------------------------------------
class TestInvoiceSentNotification:
    def test_notify_created_and_idempotent(self, make_user):
        u = make_user("invuser")
        c = Client.objects.create(user=u, company_name="Acme")
        inv = Invoice(client=c, currency="BDT")
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description="Work", quantity=Decimal("1"), unit_price=Decimal("100.00"))
        inv.recalc()
        inv.save()

        n1 = invoice_sent(inv)
        assert n1 is not None
        assert n1.template == "invoice_sent"
        assert n1.user == u
        assert Notification.objects.count() == 1

        n2 = invoice_sent(inv)
        assert n2 is None  # idempotent
        assert Notification.objects.count() == 1


# ---------------------------------------------------------------------------
class TestPaymentReceivedNotification:
    def test_payment_triggers_notification(self, make_user):
        u = make_user("payuser")
        c = Client.objects.create(user=u, company_name="Acme")
        inv = Invoice(client=c, currency="BDT")
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description="Work", quantity=Decimal("1"), unit_price=Decimal("100.00"))
        inv.recalc()
        inv.save()

        attempt, txid = initiate_payment(invoice=inv, gateway="mock", amount=Decimal("100.00"))
        payment = apply_payment_to_invoice(
            invoice=inv, amount=Decimal("100.00"), method="mock",
            gateway_trx_id=str(txid), attempt=attempt,
        )
        assert payment is not None

        notifs = Notification.objects.filter(user=u, template="payment_received")
        assert notifs.count() == 1
        assert "Payment" in notifs.first().title


# ---------------------------------------------------------------------------
class TestInvoiceOverdueNotification:
    def test_overdue_notify(self, make_user):
        from django.utils import timezone
        u = make_user("overuser")
        c = Client.objects.create(user=u, company_name="Acme")
        from datetime import date, timedelta
        inv = Invoice(client=c, currency="BDT", due_date=date.today() - timedelta(days=1))
        inv.save()
        inv.status = "sent"
        inv.save(update_fields=["status", "due_date"])

        n = invoice_overdue(inv)
        assert n is not None
        assert n.template == "invoice_overdue"
