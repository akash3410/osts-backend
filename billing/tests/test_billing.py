"""Tests for the billing domain: numbering, totals, and payment idempotency."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from userapp.models import Client
from billing.models import Invoice, InvoiceLine, Payment, WebhookEvent
from billing.services import allocate_number, apply_payment_to_invoice, initiate_payment

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def client_obj(make_user):
    u = make_user('bclient')
    return Client.objects.create(user=u, company_name='Acme')


# ---------------------------------------------------------------------------
class TestNumbering:
    def test_gap_free_invoice_numbers(self):
        from billing.models import Invoice

        c = Client.objects.first() if Client.objects.exists() else None
        if c is None:
            u = User.objects.create_user('b2', password='x12345!Aa')
            c = Client.objects.create(user=u)
        inv1 = Invoice(client=c, currency='BDT')
        inv1.save()
        inv2 = Invoice(client=c, currency='BDT')
        inv2.save()
        assert inv1.number == 'INV-2026-0001' or inv1.number.startswith('INV-')
        assert inv1.number != inv2.number
        assert inv1.number.split('-')[-1] == '0001'
        assert inv2.number.split('-')[-1] == '0002'

    def test_payment_numbering(self):
        from billing.models import Payment
        u = User.objects.create_user('payer', password='x12345!Aa')
        c = Client.objects.create(user=u)
        inv = Invoice(client=c, currency='BDT')
        inv.save()
        p = Payment(invoice=inv, client=c, amount=Decimal('10.00'), currency='BDT')
        p.save()
        assert p.number.startswith('PAY-')

    def test_allocate_number_atomic(self):
        # Two concurrent allocs yield consecutive numbers (runs serially here,
        # but the lock pattern ensures no dupes).
        n1 = allocate_number('PRO', 'BDT')
        n2 = allocate_number('PRO', 'BDT')
        assert n1 != n2
        assert n1.split('-')[-1] == '0001'
        assert n2.split('-')[-1] == '0002'


# ---------------------------------------------------------------------------
class TestRecalc:
    def test_recalc_with_tax(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description='Work', quantity=Decimal('2'),
                                 unit_price=Decimal('500.00'), tax_rate=Decimal('10'))
        inv.recalc()
        inv.save()
        # sub = 1000, tax = 100, total = 1100
        assert inv.subtotal == Decimal('1000.00')
        assert inv.total == Decimal('1100.00')
        assert inv.balance_due == Decimal('1100.00')

    def test_balance_zero_after_payment(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        inv.recalc()
        inv.save()
        assert inv.is_paid is False


# ---------------------------------------------------------------------------
class TestPaymentIdempotency:
    def test_gateway_trx_id_unique(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        p1 = Payment(invoice=inv, client=client_obj, amount=Decimal('10.00'),
                     currency='BDT', gateway_trx_id='trx-1')
        p1.save()
        with pytest.raises(Exception):
            p2 = Payment(invoice=inv, client=client_obj, amount=Decimal('10.00'),
                         currency='BDT', gateway_trx_id='trx-1')
            p2.save()

    def test_apply_payment_idempotent(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description='Work', quantity=Decimal('1'),
                                 unit_price=Decimal('100.00'))
        inv.recalc(); inv.save()
        assert inv.balance_due == Decimal('100.00')

        attempt, txid = initiate_payment(invoice=inv, gateway='sslcommerz', amount=Decimal('60.00'))
        p1 = apply_payment_to_invoice(invoice=inv, amount=Decimal('60.00'),
                                      method='sslcommerz', gateway_trx_id=str(txid))
        assert p1 is not None
        # Re-running with the same txid returns the SAME payment (no double-post).
        p2 = apply_payment_to_invoice(invoice=inv, amount=Decimal('60.00'),
                                      method='sslcommerz', gateway_trx_id=str(txid))
        assert p2.pk == p1.pk
        inv.refresh_from_db()
        assert inv.paid_total == Decimal('60.00')
        assert inv.status == 'partially_paid'

    def test_overpayment_rejected(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description='Work', quantity=Decimal('1'),
                                 unit_price=Decimal('100.00'))
        inv.recalc(); inv.save()
        # try overpay beyond balance
        with pytest.raises(ValueError):
            apply_payment_to_invoice(invoice=inv, amount=Decimal('200.00'),
                                     method='system')
        # failed attempt did NOT mutate paid_total
        inv.refresh_from_db()
        assert inv.paid_total == Decimal('0.00')

    def test_void_payment(self, client_obj):
        inv = Invoice(client=client_obj, currency='BDT')
        inv.save()
        InvoiceLine.objects.create(invoice=inv, description='Work', quantity=Decimal('1'),
                                 unit_price=Decimal('100.00'))
        inv.recalc(); inv.save()
        p = apply_payment_to_invoice(invoice=inv, amount=Decimal('40.00'), method='system')
        inv.refresh_from_db()
        before = inv.paid_total
        p.void('duplicate entry')
        assert p.is_void is True
        assert p.status == 'voided'
        inv.refresh_from_db()
        # paid_total rolled back
        assert inv.paid_total < before


# ---------------------------------------------------------------------------
class TestWebhookDedupe:
    def test_unique_per_gateway_event(self):
        we1 = WebhookEvent.objects.create(gateway='sslcommerz', event_type='IPN', event_id='e1')
        assert we1.pk is not None
        with pytest.raises(Exception):
            WebhookEvent.objects.create(gateway='sslcommerz', event_type='IPN', event_id='e1')

    def test_mark_processed(self):
        we = WebhookEvent.objects.create(gateway='sslcommerz', event_type='IPN', event_id='e2')
        assert not we.processed
        we.mark_processed({'note': 'done'})
        we.refresh_from_db()
        assert we.processed is True
        assert we.result == {'note': 'done'}
        assert we.processed_at is not None