"""Business logic for billing.

Views should:
  1. run forms, then
  2. delegate to a service function here, then
  3. redirect / render.

Keeps money math (Decimal), allocation, state transitions in one place so the
future SSLCommerz adapter and API both share the exact same paths.
"""
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    CURRENCY_DEFAULT,
    DocumentStatus,
    Invoice,
    InvoiceLine,
    NumberSequence,
    Payment,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentMethod,
    PaymentStatus,
    Proposal,
    ProposalLine,
    ProposalStatus,
)


# ----------------------------------------------------------------- numbering
@transaction.atomic
def allocate_number(domain, currency):
    """Allocate the next gap-free number for a (domain, current year) pair.

    Domain examples: 'INV', 'PAY', 'PRO'. Format: '{DOMAIN}-{YEAR}-{NNNN}'.
    Concurrency-safety: each (domain, year) allocation runs under
    ``select_for_update`` on the shared NumberSequence row, so two concurrent
    requests cannot receive the same number.
    """
    from django.utils import timezone as tz

    year = tz.now().year
    seq, _ = NumberSequence.objects.select_for_update().get_or_create(
        domain=domain, year=year, defaults={'last': 0}
    )
    seq.last += 1
    seq.save(update_fields=['last', 'updated_at'])
    return f'{domain}-{year}-{seq.last:04d}'


# ------------------------------------------------------- invoice creation
def create_invoice_from_proposal(proposal, issued_at=None, due_date=None):
    """Convert an accepted proposal into a draft invoice. Idempotent across a
    single proposal: calling twice returns the existing invoice."""
    from django.utils import timezone

    existing = Invoice.objects.filter(proposal=proposal).first()
    if existing:
        return existing
    if not proposal.can_convert():
        raise ValueError(f'Proposal {proposal.number} cannot be converted (status={proposal.status}).')

    from django.utils import timezone as tz

    invoice = Invoice(
        client=proposal.client,
        project=proposal.project,
        proposal=proposal,
        currency=proposal.currency,
        issued_at=issued_at or tz.now().date(),
        due_date=due_date,
        notes=proposal.notes,
    )
    # Allocate number in a transaction.
    invoice.save()
    for line in proposal.lines.all():
        InvoiceLine.objects.create(
            invoice=invoice,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            tax_rate=line.tax_rate,
        )
    invoice.recalc()
    invoice.save(update_fields=['subtotal', 'tax_total', 'total', 'updated_at'])
    proposal.status = ProposalStatus.ACCEPTED  # already, but keeps consistency
    return invoice


def finalize_invoice(invoice):
    """Recalc totals and advance status to 'sent' if still draft."""
    invoice.recalc()
    from django.utils import timezone

    if invoice.status == 'draft':
        invoice.issued_at = invoice.issued_at or timezone.now().date()
        invoice.mark_sent()
    else:
        invoice.save(update_fields=['subtotal', 'tax_total', 'total', 'updated_at'])
    return invoice


# ---------------------------------------------------------------- payments
@transaction.atomic
def apply_payment_to_invoice(*, invoice, amount, method='system', paid_at=None,
                             reference='', gateway_trx_id=None,
                             attempt=None, currency=None):
    """Record an immutable payment receipt + update the invoice's paid_total.

    Idempotency levels:
      1. If gateway_trx_id is given and already exists, return the existing
         Payment (no dupes).
      2. Lock the invoice row (select_for_update) so concurrent callbacks
         cannot double-apply the same amount.
      3. Re-read invoice.paid_total after the lock and bail if the payment
         would exceed total (prevents over-payment under a race).
    """
    from django.utils import timezone
    from django.db import transaction

    currency = currency or invoice.currency

    # Idempotency (level 1).
    if gateway_trx_id:
        existing = Payment.objects.filter(
            gateway_trx_id=gateway_trx_id, is_void=False,
        ).first()
        if existing:
            return existing

    # Lock the invoice.
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)

    if amount <= 0:
        raise ValueError('Payment amount must be > 0')
    if invoice.balance_due + Decimal('0.001') < amount:
        raise ValueError(
            f'Payment amount {amount} exceeds outstanding balance {invoice.balance_due}.'
        )

    # Mark invoice overdue if past due.
    if (invoice.due_date is not None and invoice.due_date < timezone.now().date()
            and invoice.status in ('sent', 'partially_paid')):
        invoice.status = DocumentStatus.OVERDUE

    payment = Payment(
        invoice=invoice,
        client=invoice.client,
        amount=amount,
        currency=currency,
        method=method,
        paid_at=paid_at or timezone.now(),
        reference=reference,
        gateway_trx_id=gateway_trx_id or None,
        attempt=attempt,
    )
    payment.save()  # allocates number

    # Idempotency (level 3): update paid_total atomically.
    invoice.paid_total = (invoice.paid_total or Decimal('0.00')) + amount
    invoice.paid_total = invoice.paid_total.quantize(Decimal('0.01'))
    if invoice.is_paid:
        invoice.status = DocumentStatus.PAID
        invoice.paid_at = timezone.now().date()
    else:
        if invoice.status not in (DocumentStatus.PAID,):
            invoice.status = DocumentStatus.PARTIALLY_PAID
    invoice.save(update_fields=['paid_total', 'status', 'paid_at', 'updated_at'])

    # Link back the attempt, if any.
    if attempt is not None:
        attempt.paid_payment = payment
        attempt.save(update_fields=['paid_payment', 'updated_at'])

    return payment


def void_payment(payment, reason=''):
    """Void a payment: appends the reversal flag (never deletes the row) and
    rolls back the invoice's paid_total via Payment.void()."""
    if not payment.is_void:
        payment.void(reason)
    return payment


# --------------------------------------------------- payment gateway attempt
@transaction.atomic
def initiate_payment(*, invoice, gateway='sslcommerz', amount=None):
    """Create an attempt record + a unique UUID (tran_id) to send to gateway.

    Returns (attempt, transaction_id_string). The adapter then forms the
    gateway redirect/form with txid as tran_id.
    """
    if amount is None:
        amount = invoice.balance_due
    if amount <= 0:
        raise ValueError('Nothing to pay.')
    attempt = PaymentAttempt.objects.create(
        invoice=invoice,
        client=invoice.client,
        amount=amount,
        currency=invoice.currency,
        gateway=gateway,
        status=PaymentAttemptStatus.INITIATED,
    )
    return attempt, str(attempt.txid)


# --------------------------------------------------------- proposal conversion
def finalize_proposal(proposal):
    if proposal.status == ProposalStatus.DRAFT:
        proposal.status = ProposalStatus.SENT
        proposal.save(update_fields=['status', 'updated_at'])
    return proposal