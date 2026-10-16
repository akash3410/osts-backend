"""Billing web views + webhook listener.

Port (web, not API) for the invoicing flow. A customer clicks 'Pay', we
create a PaymentAttempt + tran_id, redirect to the gateway, the gateway calls
back to /webhook/, and we validate server-side before applying a payment.

Access control:
  * Customers see only their own invoices (scoped via ``invoice.client.user == request.user``)
  * Staff/admin see everything (the user_passes_test role decorators handle it).
"""
import json
import logging
from decimal import Decimal
from urllib.parse import urlparse

from django.contrib import messages as dj_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.decorators import staff_required, roles_required
from userapp.models import Client
from projects.models import Project

from .models import Invoice, PaymentAttempt, WebhookEvent, PaymentAttemptStatus
from .services import initiate_payment, apply_payment_to_invoice, allocate_number
from .gateways import (available_gateways, get_gateway, GatewayResponse,
                      InitiationResult)

User = get_user_model()
log = logging.getLogger(__name__)


def _client_for(request):
    """Return the Client bound to the current user, or None if none exists."""
    return Client.objects.filter(user=request.user).first()


def _invoice_access_ok(user, invoice):
    """A non-staff user may only touch their own invoice."""
    if user.is_staff or user.is_superuser:
        return True
    client = Client.objects.filter(user=user).first()
    return client is not None and invoice.client_id == client.id


# ---------------------------------------------------------------------------
# Portal invoice views
@login_required
def invoice_detail_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not _invoice_access_ok(request.user, invoice):
        return redirect(settings.LOGIN_URL)
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_list_view(request):
    if request.user.is_staff or request.user.is_superuser:
        invoices = Invoice.objects.all().order_by('-created_at')
    else:
        client = _client_for(request)
        invoices = Invoice.objects.filter(client=client).order_by('-created_at') if client else Invoice.objects.none()
    return render(request, 'billing/invoice_list.html', {'invoices': invoices})


# ---------------------------------------------------------------------------
# Payment initiation
@login_required
@require_POST
def payment_initiate_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    if not _invoice_access_ok(request.user, invoice):
        return redirect(settings.LOGIN_URL)

    if invoice.is_paid:
        dj_messages.info(request, 'This invoice is already paid.')
        return redirect('billing:invoice_detail', pk=invoice_id)

    try:
        amount = Decimal(request.POST.get('amount') or invoice.balance_due)
    except Exception:
        dj_messages.error(request, 'Invalid amount.')
        return redirect('billing:invoice_detail', pk=invoice_id)

    if amount <= 0 or amount > invoice.balance_due:
        dj_messages.error(
            request,
            f'Amount must be between 0.01 and {invoice.balance_due}.',
        )
        return redirect('billing:invoice_detail', pk=invoice_id)

    gateway_name = request.POST.get('gateway') or 'mock'
    try:
        gateway = get_gateway(gateway_name)
    except ValueError:
        dj_messages.error(request, f'Unknown gateway: {gateway_name}')
        return redirect('billing:invoice_detail', pk=invoice_id)

    # Build the gateway credentials from env-ish settings. Keep them out of
    # the template. In a real deploy these come from an encrypted SiteConfig
    # row or env vars; here we read whatever the settings module provides.
    creds = _gateway_credentials(gateway_name)

    # Create the attempt + tran_id (UUID) in our DB.
    attempt, txid = initiate_payment(invoice=invoice, gateway=gateway_name, amount=amount)

    success_url = request.build_absolute_uri('/billing/webhook/sslcommerz/return/')
    fail_url = request.build_absolute_uri('/billing/webhook/sslcommerz/return/?failed=1')
    cancel_url = request.build_absolute_uri('/billing/webhook/sslcommerz/return/?cancelled=1')

    # Gateway session creation (redirect URL or form).
    res: InitiationResult = gateway.initiate(
        tran_id=txid,
        amount=amount,
        currency=invoice.currency,
        client_ip=_client_ip(request),
        success_url=success_url,
        fail_url=fail_url,
        cancel_url=cancel_url,
        customer_email=getattr(invoice.client.user, 'email', '') or '',
        description=f'Invoice {invoice.number}',
    )

    if not res.success:
        attempt.status = PaymentAttemptStatus.FAILED
        attempt.error = res.message
        attempt.save(update_fields=['status', 'error', 'updated_at'])
        dj_messages.error(request, f'Payment could not be initiated: {res.message}')
        return redirect('billing:invoice_detail', pk=invoice_id)

    # Store gateway ref on attempt and mark pending.
    attempt.status = PaymentAttemptStatus.PENDING
    attempt.raw_response = res.raw or {}
    attempt.save(update_fields=['status', 'raw_response', 'updated_at'])

    if gateway_name == 'mock':
        # For the dev mock, we hand a hidden form that auto-submits the
        # to-be-returned parameters. Cheaper than a redirect loop.
        return render(request, 'billing/payment_form_auto.html', {
            'gateway_url': res.gateway_url,
            'attempt': attempt, 'invoice': invoice, 'txid': txid,
        })
    return redirect(res.gateway_url)


def _client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def _gateway_credentials(gateway_name):
    import os
    name = gateway_name.lower()
    if name == 'sslcommerz':
        return {
            'store_id': os.environ.get('SSLZ_STORE_ID', ''),
            'store_password': os.environ.get('SSLZ_STORE_PASSWORD', ''),
            'sandbox': os.environ.get('SSLZ_SANDBOX', '1') == '1',
        }
    if name == 'stripe':
        return {'secret_key': os.environ.get('STRIPE_SECRET_KEY', '')}
    return {}


# ---------------------------------------------------------------------------
# Webhook (idempotent listener)
@csrf_exempt
@require_POST
def sslcommerz_webhook_view(request):
    payload = _request_data(request)
    log.info('SSLCommerz webhook received: %s', {k: payload.get(k) for k in
        ('tran_id', 'val_id', 'status', 'currency_amount')})

    # extract tran_id (our UUID)
    tran_id = payload.get('tran_id') or payload.get('tran_id')
    if not tran_id:
        return HttpResponse('Bad Request: missing tran_id', status=400)

    # Idempotency anchor #1: WebhookEvent row (dedupe on event id).
    try:
        event_id = payload.get('val_id') or payload.get('bank_tran_id') or f"{tran_id}:{payload.get('status')}"
    except Exception:
        event_id = payload.get('bank_tran_id') or payload.get('tran_id')

    from django.db import IntegrityError
    try:
        event = WebhookEvent.objects.create(
            gateway='sslcommerz', event_type='IPN', event_id=str(event_id),
            payload=payload,
        )
    except IntegrityError:
        # Duplicate webhook - check if processed already.
        existing = WebhookEvent.objects.filter(
            gateway='sslcommerz', event_type='IPN', event_id=str(event_id),
        ).first()
        if existing and existing.processed:
            return HttpResponse('OK')
        event = existing
        # fall through — re-attempt processing if it previously failed

    try:
        attempt = PaymentAttempt.objects.select_related('invoice').get(txid=tran_id)
    except PaymentAttempt.DoesNotExist:
        dj_messages.error(request, 'Unknown tran_id')
        event.mark_processed({'result': 'unknown tran_id'})
        return HttpResponse('OK')  # 200 to stop gateway retries

    if attempt.status == PaymentAttemptStatus.SUCCESS and attempt.paid_payment_id:
        event.mark_processed({'result': 'already processed via attempt'})
        return HttpResponse('OK')

    gw = get_gateway('sslcommerz', **_gateway_credentials('sslcommerz'))
    trusted_amount = attempt.amount
    trusted_currency = attempt.currency
    res = gw.validate(
        tran_id=str(attempt.txid),
        val_id=payload.get('val_id'),
        amount=trusted_amount,
        currency=trusted_currency,
        ipn_payload=payload,
    )

    attempt.raw_response = (res.raw or {})
    attempt.validation_status = res.status
    attempt.validated_amount = res.amount
    attempt.gateway_tran_id = res.gateway_tran_id
    attempt.gateway_bank_tran_id = payload.get('bank_tran_id', attempt.gateway_bank_tran_id)

    WebhookEvent(...).pk  # no-op sanity

    WebhookEvent(...).pk  # no-op sanity

    if not res.ok or not gw.is_validation_ok(trusted_amount=trusted_amount, response=res):
        attempt.status = PaymentAttemptStatus.FAILED
        attempt.error = res.message or 'validation failed'
        attempt.save(update_fields=['status', 'error', 'raw_response',
                                    'validation_status', 'validated_amount',
                                    'gateway_tran_id', 'gateway_bank_tran_id', 'updated_at'])
        event.mark_processed({'result': 'validation failed'})
        return HttpResponse('FAIL', status=400)

    # Success — apply payment only here (server-validated).
    attempt.status = PaymentAttemptStatus.SUCCESS
    attempt.save(update_fields=['status', 'raw_response', 'validation_status', 'validated_amount',
                                'gateway_tran_id', 'gateway_bank_tran_id', 'updated_at'])

    gateway_trx_id = res.gateway_tran_id or payload.get('bank_tran_id') or str(res.raw.get('tran_id'))
    payment = apply_payment_to_invoice(
        invoice=attempt.invoice, amount=attempt.amount,
        method='sslcommerz', gateway_trx_id=gateway_trx_id,
        attempt=attempt,
        currency=attempt.currency,
    )
    attempt.paid_payment = payment
    attempt.save(update_fields=['paid_payment', 'updated_at'])
    invoice = attempt.invoice
    invoice.mark_paid()
    event.mark_processed({'result': 'paid', 'payment_number': payment.number})
    return HttpResponse('OK')


@csrf_exempt
def sslcommerz_return_view(request):
    """Browser redirect after a payment attempt (success/fail/cancel).

    NOTE: this is NOT where we settle. Settlement happens ONLY in the
    webhook above after server-side validation. Returning from this path just
    sends the user back to the invoice page with status context.
    """
    payload = _request_data(request)
    tran_id = payload.get('tran_id')
    failed = 'failed' in request.GET.get('failed', '') or payload.get('status') == 'FAILED'
    cancelled = 'cancelled' in request.GET.get('cancelled', '')
    if tran_id:
        try:
            attempt = PaymentAttempt.objects.get(txid=tran_id)
            if attempt.status == PaymentAttemptStatus.SUCCESS:
                dj_messages.success(request, 'Payment received — invoice will update shortly.')
            elif cancelled:
                dj_messages.info(request, 'Payment cancelled.')
            elif failed:
                dj_messages.warning(request, 'Payment failed. Please try again.')
        except PaymentAttempt.DoesNotExist:
            pass
    return redirect('billing:invoice_detail', pk=attempt.invoice_id if tran_id else 1)


# In views add after sslcommerz_return_view definition (end of file)
def _mock_pay_view(request, txid):
    """Dev-only: auto-settles a mock-gateway attempt without an external call."""
    try:
        attempt = PaymentAttempt.objects.get(txid=txid)
    except PaymentAttempt.DoesNotExist:
        return HttpResponse('Unknown attempt', status=404)
    if attempt.status == PaymentAttemptStatus.SUCCESS:
        return redirect('billing:invoice_detail', pk=attempt.invoice_id)
    # Simulate server-side validation via the mock gateway.
    gw = get_gateway('mock')
    res = gw.validate(tran_id=str(attempt.txid), amount=attempt.amount,
                      currency=attempt.currency, ipn_payload={})
    if gw.is_validation_ok(trusted_amount=attempt.amount, response=res):
        try:
            payment = apply_payment_to_invoice(
                invoice=attempt.invoice, amount=attempt.amount,
                method='mock', gateway_trx_id=res.gateway_tran_id or f'mock-{txid}',
                attempt=attempt, currency=attempt.currency,
            )
            attempt.paid_payment = payment
            attempt.status = PaymentAttemptStatus.SUCCESS
            attempt.save(update_fields=['paid_payment', 'status', 'updated_at'])
            attempt.invoice.mark_paid() if hasattr(attempt.invoice, 'mark_paid') else None
            dj_messages.success(request, 'Mock payment received.')
        except Exception as e:
            log.warning('mock settle failed: %s', e)
            attempt.status = PaymentAttemptStatus.FAILED
            attempt.error = str(e)
            attempt.save(update_fields=['status', 'error', 'updated_at'])
            dj_messages.error(request, f'Mock payment failed: {e}')
    else:
        attempt.status = PaymentAttemptStatus.FAILED
        attempt.error = 'validation failed'
        attempt.save(update_fields=['status', 'error', 'updated_at'])
        dj_messages.error(request, 'Mock validation failed.')
    return redirect('billing:invoice_detail', pk=attempt.invoice_id)
    data = {}
    if request.method == 'POST':
        data.update(request.POST.dict())
    data.update(request.GET.dict())
    # Also parse a raw JSON body if present.
    if request.body:
        content_type = request.META.get('CONTENT_TYPE', '')
        if 'json' in content_type:
            try:
                data.update(json.loads(request.body.decode('utf-8')))
            except Exception:
                pass
    return data