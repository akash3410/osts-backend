"""SSLCommerz adapter.

Implements the SSLCommerz initiation (session creation) + the server-side
validation API. ALWAYS call :meth:`validate`, which hits the gateway's
validation server; IPN / redirect values are never trusted verbatim.

Important notes:
  * ``tran_id`` MUST equal our internal PaymentAttempt.txid (UUID). This is
    the first idempotency anchor.
  * Store ID + password MUST come from env (``SSLZ_STORE_ID``,
    ``SSLZ_STORE_PASSWORD``); ``SSLZ_SANDBOX=1`` switches endpoints.
  * SSLCommerz IPN endpoint is multi-section. Register it in the dashboard
    so the gateway calls it; our webhook view idempotently processes.
"""
import requests
from decimal import Decimal
from urllib.parse import urlencode

from billing.gateways.base import GatewayResponse, InitiationResult, PaymentGateway, register_gateway

# http:// → https enforced.
TEST_BASE = 'https://sandbox.sslcommerz.com'
PROD_BASE = 'https://securepay.sslcommerz.com'


class SslCommerzGateway(PaymentGateway):
    name = 'sslcommerz'

    def _base(self):
        return TEST_BASE if self.sandbox else PROD_BASE

    def initiate(self, *, tran_id, amount, currency, client_ip, success_url,
                 fail_url, cancel_url, customer_email, description) -> InitiationResult:
        payload = {
            'store_id': self.store_id,
            'store_passwd': self.store_password,
            'total_amount': str(amount),
            'currency': currency,
            'tran_id': tran_id,
            'success_url': success_url,
            'fail_url': fail_url,
            'cancel_url': cancel_url,
            'cus_name': 'Customer',
            'cus_email': customer_email or 'customer@example.com',
            'cus_add1': 'Dhaka', 'cus_add2': 'Dhaka', 'cus_city': 'Dhaka',
            'cus_state': 'Dhaka', 'cus_postcode': '1207', 'cus_country': 'Bangladesh',
            'cus_phone': '01700000000', 'cus_fax': '',
            'ship_name': 'NA', 'ship_add1': 'NA', 'ship_add2': 'NA',
            'ship_city': 'NA', 'ship_state': 'NA', 'ship_postcode': 'NA',
            'ship_country': 'NA', 'shipping_method': 'NO',
            'product_name': description[:80] or 'Invoice payment',
            'product_category': 'services', 'product_profile': 'general',
            'multi_card_name': '', 'num_of_item': 1,
            'method': 'sslcz',
        }
        try:
            r = requests.post(f'{self._base()}/gwprocess/v4/api.php', data=payload, timeout=30)
            data = r.json()
        except Exception as e:
            return InitiationResult(success=False, message=f'gateway unreachable: {e}')

        if data.get('status') == 'success' and data.get('GatewayPageURL'):
            return InitiationResult(success=True, gateway_url=data['GatewayPageURL'], tran_id=tran_id, raw=data)
        return InitiationResult(success=False, message=data.get('failedreason') or 'session creation failed', raw=data)

    def validate(self, *, tran_id, val_id=None, amount=None, currency=None,
                 ipn_payload=None) -> GatewayResponse:
        ipn_payload = ipn_payload or {}
        params = {
            'val_id': val_id or ipn_payload.get('val_id'),
            'store_id': self.store_id,
            'store_passwd': self.store_password,
            'format': 'json',
        }
        if not params['val_id']:
            # No val_id even in payload — cannot validate.
            return GatewayResponse(ok=False, status='none', message='missing val_id')
        try:
            r = requests.post('https://securepay.sslcommerz.com/validator/api/validationserverAPI.php'
                              if not self.sandbox else 'https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php',
                              data=params, timeout=30)
            data = r.json()
        except Exception as e:
            return GatewayResponse(ok=False, status='error', message=f'validation unreachable: {e}')

        status = data.get('status', '')
        amt = data.get('currency_amount') or data.get('amount')
        try:
            amt = Decimal(str(amt)) if amt is not None else None
        except Exception:
            amt = None

        ok = status in ('VALID', 'VALIDATED', 'VALIDATED')
        return GatewayResponse(
            ok=ok, status='success' if ok else status,
            amount=amt,
            gateway_tran_id=data.get('bank_tran_id') or data.get('bkash_payment_id'),
            message=data.get('error', ''),
            raw=data,
        )


register_gateway('sslcommerz', lambda **kw: SslCommerzGateway(**kw))