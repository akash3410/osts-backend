"""Billing domain: proposals, invoices, payments, and payment-attempt journal.

Money conventions (applied everywhere in this app):
  * Every money column is DecimalField(max_digits=12, decimal_places=2) — no
    float arithmetic, ever.
  * Every document carries a ``currency`` CharField(3); converted values are
    out of scope here.
  * Cached totals are recomputed via ``recalc()`` (never trusted as input).

Invariants (enforced via constraints + select_for_update):
  * Gap-free numbers via NumberSequence (no MAX()+1).
  * Append-only Payment ledger: rows are NEVER deleted — only voided.
  * Three-level idempotency for gateway payments:
      1. WebhookEvent: dedupe by gateway (event type, event id) primary key
      2. Payment: unique ``gateway_trx_id``
      3. Invoice: ``select_for_update`` when applying a payment
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from dashboardapp.models import Service
from projects.models import Project
from userapp.models import Client


# ------------------------------------------------------------------- choices
class DocumentStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'
    PARTIALLY_PAID = 'partially_paid', 'Partially paid'
    PAID = 'paid', 'Paid'
    OVERDUE = 'overdue', 'Overdue'
    VOID = 'void', 'Void'      # what was "void" vs "cancelled" — voided
    CANCELLED = 'cancelled', 'Cancelled'


class ProposalStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'
    EXPIRED = 'expired', 'Expired'


class PaymentMethod(models.TextChoices):
    SSLCOMMERCZ = 'sslcommerz', 'SSLCommerz'
    STRIPE = 'stripe', 'Stripe'
    BKASH = 'bkash', 'bKash'
    BANK = 'bank', 'Bank transfer'
    CASH = 'cash', 'Cash'
    SYSTEM = 'system', 'System adjustment'


class PaymentStatus(models.TextChoices):
    RECEIVED = 'received', 'Received'
    REFUNDED = 'refunded', 'Refunded'
    VOID = 'voided', 'Voided'


class PaymentAttemptStatus(models.TextChoices):
    INITIATED = 'initiated', 'Initiated'   # created in our DB
    PENDING = 'pending', 'Pending gateway'  # user redirected
    SUCCESS = 'success', 'Gateway success (validated server-side)'
    FAILED = 'failed', 'Gateway failed'
    EXPIRED = 'expired', 'Expired/unconfirmed'


class WebhookStatus(models.TextChoices):
    RECEIVED = 'received', 'Received (unprocessed)'
    PROCESSED = 'processed', 'Processed'
    DUPLICATE = 'duplicate', 'Duplicate (skipped)'
    FAILED = 'failed', 'Processing failed'


CURRENCY_DEFAULT = 'BDT'


# ---------------------------------------------------------- numbering
class NumberSequence(TimeStampedModel):
    """Gap-free numbering. NEVER use MAX()+1.

    Each (domain, year) row tracks the last number handed out. Allocation is
    atomic via ``select_for_update()`` at allocation time — running two
    concurrent requests serialises on the row lock.
    """
    domain = models.CharField(max_length=20, db_index=True)
    year = models.PositiveSmallIntegerField(db_index=True)
    last = models.PositiveIntegerField(default=0)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=['domain', 'year'], name='numbersequence_domain_year_unique'
            ),
        ]

    def __str__(self):
        return f'{self.domain}-{self.year}: {self.last}'


# -------------------------------------------------------------- proposals
class ProposalLine(TimeStampedModel):
    proposal = models.ForeignKey('Proposal', on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    # cached; recomputed
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def recalc(self):
        sub = (self.quantity * self.unit_price).quantize(Decimal('0.01'))
        tax = (sub * self.tax_rate / 100).quantize(Decimal('0.01'))
        self.line_subtotal = sub
        self.line_total = sub + tax
        return self.line_total

    def __str__(self):
        return f'{self.quantity}x {self.description}'


class Proposal(TimeStampedModel):
    """Customer-facing quote/proposal. Converts to an Invoice when accepted."""
    number = models.CharField(max_length=32, unique=True, blank=True, editable=False)

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='proposals')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='proposals')

    status = models.CharField(max_length=15, choices=ProposalStatus.choices, default=ProposalStatus.DRAFT, db_index=True)

    issued_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    currency = models.CharField(max_length=3, default=CURRENCY_DEFAULT)
    notes = models.TextField(blank=True)

    def recalc(self):
        sub = Decimal('0.00')
        tax = Decimal('0.00')
        for line in self.lines.all():
            line.recalc()
            line.save(update_fields=['line_subtotal', 'line_total', 'updated_at'])
            sub += line.line_subtotal
            tax += line.line_total - line.line_subtotal
        self.subtotal = sub.quantize(Decimal('0.01'))
        self.tax_total = tax.quantize(Decimal('0.01'))
        self.total = (self.subtotal + self.tax_total - (self.discount or Decimal('0.00'))).quantize(Decimal('0.01'))
        return self.total

    def is_accepted(self):
        return self.status == ProposalStatus.ACCEPTED

    def can_convert(self):
        return self.status == ProposalStatus.ACCEPTED

    class Meta(TimeStampedModel.Meta):
        ordering = ['-created_at']


# --------------------------------------------------------------------------- invoices
class InvoiceLine(TimeStampedModel):
    invoice = models.ForeignKey('Invoice', on_delete=models.CASCADE, related_name='lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    # Cached totals — recomputed by Invoice.recalc()
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def recalc(self):
        sub = (self.quantity * self.unit_price).quantize(Decimal('0.01'))
        tax = (sub * self.tax_rate / 100).quantize(Decimal('0.01'))
        self.line_subtotal = sub
        self.line_total = sub + tax
        return self.line_total

    def __str__(self):
        return f'{self.quantity}x {self.description}'


class Invoice(TimeStampedModel):
    """The receivable. Number is gap-free via NumberSequence allocation."""
    number = models.CharField(max_length=32, unique=True, blank=True, editable=False)

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='invoices')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    # Optional source proposal that produced this invoice.
    proposal = models.ForeignKey(Proposal, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')

    status = models.CharField(max_length=15, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT, db_index=True)

    issued_at = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateField(null=True, blank=True)

    # Cached totals.
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # sum of receipts

    currency = models.CharField(max_length=3, default=CURRENCY_DEFAULT)
    payment_terms = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ['-created_at']
        constraints = [
            # An invoice cannot be overpaid vs. the cached total.
            models.CheckConstraint(
                condition=models.Q(paid_total__lte=models.F('total'))
                | models.Q(status__in=('draft', 'void', 'cancelled')),
                name='invoice_paid_lte_total_or_void',
            ),
        ]

    def recalc(self):
        """Recompute all line + document totals. Call after any line change."""
        sub = Decimal('0.00')
        tax = Decimal('0.00')
        for line in self.lines.all():
            line.recalc()
            line.save(update_fields=['line_subtotal', 'line_total', 'updated_at'])
            sub += line.line_subtotal
            tax += line.line_total - line.line_subtotal
        self.subtotal = sub.quantize(Decimal('0.01'))
        self.tax_total = tax.quantize(Decimal('0.01'))
        self.total = (self.subtotal + self.tax_total - (self.discount or Decimal('0.00'))).quantize(Decimal('0.01'))
        return self.total

    @property
    def balance_due(self):
        return (Decimal(self.total or 0) - Decimal(self.paid_total or 0)).quantize(Decimal('0.01'))

    @property
    def is_paid(self):
        return self.paid_total >= self.total and self.total > 0

    # ------------------------ status transitions
    def mark_sent(self):
        if self.status not in (DocumentStatus.DRAFT,):
            return self
        self.status = DocumentStatus.SENT
        self.save(update_fields=['status', 'updated_at'])
        return self

    def mark_paid(self, paid_at=None):
        from django.utils import timezone

        self.status = DocumentStatus.PAID
        if paid_at is not None:
            self.paid_at = paid_at
        elif self.paid_at is None:
            self.paid_at = timezone.now().date()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])
        return self

    def void(self, reason=''):
        # Void references a payment settlement; never delete the row.
        self.status = DocumentStatus.VOID
        if reason:
            self.notes = (self.notes + '\n' + f'VOIDED: {reason}').strip()
        self.save(update_fields=['status', 'notes', 'updated_at'])
        return self

    def __str__(self):
        return self.number or f'Invoice#{self.pk}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._finalized = bool(self.number)

    def save(self, *args, **kwargs):
        # Allocate a gap-free number the first time the invoice is saved.
        if not self.number:
            from billing.services import allocate_number
            self.number = allocate_number('INV', self.currency)
        super().save(*args, **kwargs)


# --------------------------------------------------------------------------- payments
class Payment(TimeStampedModel):
    """Append-only ledger. NEVER delete — void instead."""
    number = models.CharField(max_length=32, unique=True, blank=True, editable=False)

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments', null=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payments')

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    currency = models.CharField(max_length=3, default=CURRENCY_DEFAULT)

    method = models.CharField(max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.SYSTEM)
    status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.RECEIVED, db_index=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=200, blank=True, help_text='Bank slip / gateway reference / cheque #')

    # Idempotency for gateway payments: this must be globally unique.
    gateway_trx_id = models.CharField(max_length=120, blank=True, null=True, unique=True, db_index=True)

    is_void = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)

    # Link to the attempt journal entry if one exists.
    attempt = models.OneToOneField('PaymentAttempt', on_delete=models.SET_NULL, null=True, blank=True, related_name='payment')


    class Meta(TimeStampedModel.Meta):
        ordering = ['-paid_at', '-created_at']
        indexes = [
            models.Index(fields=['client', 'status']),
            models.Index(fields=['invoice', 'status']),
        ]
        constraints = [
            # Once voided, only the void flag + reason were changed — we can't
            # enforce that here, but we DO enforce a void row keeps its amount
            # (auditable). The MIN validator above already blocks zero/negative.
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name='payment_amount_positive'
            ),
        ]

    def void(self, reason=''):
        if self.is_void:
            return self
        from django.utils import timezone
        self.is_void = True
        self.voided_at = timezone.now()
        self.void_reason = reason
        self.status = PaymentStatus.VOID
        self.save(update_fields=['is_void', 'voided_at', 'void_reason', 'status', 'updated_at'])
        # Roll back the receivable's paid_total so the invoice re-opens.
        if self.invoice_id:
            invoice = self.invoice
            new_paid = (invoice.paid_total or Decimal('0.00')) - self.amount
            if new_paid < 0:
                new_paid = Decimal('0.00')
            invoice.paid_total = new_paid.quantize(Decimal('0.01'))
            if invoice.status == DocumentStatus.PAID:
                invoice.status = 'partially_paid' if invoice.paid_total > 0 else 'sent'
            invoice.save(update_fields=['paid_total', 'status', 'updated_at'])
        return self

    def __str__(self):
        return self.number or f'Payment#{self.pk}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._finalized = bool(self.number)

    def save(self, *args, **kwargs):
        if not self.number:
            from billing.services import allocate_number
            self.number = allocate_number('PAY', self.currency)
        super().save(*args, **kwargs)


class PaymentAttempt(TimeStampedModel):
    """Gateway attempt journal. Created on intent, updated by webhook + validation.

    tran_id (txid) is OUR UUID, sent to the gateway as ``tran_id`` and stored
    server-side. We never trust the IPN/redirect params; we always call the
    gateway's validation API server-side and compare tran_id + amount.
    """
    txid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payment_attempts')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payment_attempts')

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=CURRENCY_DEFAULT)

    gateway = models.CharField(max_length=20, choices=[
        ('sslcommerz', 'SSLCommerz'), ('stripe', 'Stripe'), ('bkash', 'bKash'),
    ])
    status = models.CharField(max_length=12, choices=PaymentAttemptStatus.choices, default=PaymentAttemptStatus.INITIATED, db_index=True)

    # Gateway response (sanitized + raw), populated after server-side call.
    gateway_tran_id = models.CharField(max_length=120, blank=True, help_text="Gateway's own transaction id")
    gateway_bank_tran_id = models.CharField(max_length=120, blank=True)
    validated_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    validation_status = models.CharField(max_length=50, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    paid_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_attempt')

    error = models.CharField(max_length=300, blank=True)

    class Meta(TimeStampedModel.Meta):
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.gateway}:{self.txid} -> {self.status}'


class WebhookEvent(TimeStampedModel):
    """Idempotency anchor #1 for gateway webhooks.

    We insert a row keyed by (gateway, event_type, event_id) on the *very
    first* processing line. A duplicate webhook either collides on the unique
    constraint and is skipped (``duplicate``) or returns early when already
    processed. Race safety comes from a unique constraint, not a lock-then-check.
    """
    gateway = models.CharField(max_length=20)
    event_type = models.CharField(max_length=60, db_index=True)
    event_id = models.CharField(max_length=120)
    payload = models.JSONField(default=dict, blank=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True, help_text='What the handler did.')

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=['gateway', 'event_type', 'event_id'],
                name='webhookevent_unique_per_gateway_event',
            ),
        ]
        indexes = [
            models.Index(fields=['processed', 'created_at']),
        ]

    def mark_processed(self, result=None):
        from django.utils import timezone
        self.processed = True
        self.processed_at = timezone.now()
        if result is not None:
            self.result = result
        self.save(update_fields=['processed', 'processed_at', 'result', 'updated_at'])


# forward-declared models so string refs above resolve at migration generation
from projects.models import Project  # noqa: E402