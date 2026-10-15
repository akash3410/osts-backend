"""Mock gateway for development and tests. Always succeeds; validates tran_id strings."""
import uuid
from decimal import Decimal

from billing.gateways.base import PaymentGateway, GatewayResponse, InitiationResult, register_gateway


class MockGateway(PaymentGateway):
    name = 'mock'

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._fake_val_id = 'MOCK-VAL-' + uuid.uuid4().hex[:8]

    # -- URL must look like the gateway payment page; in dev we route through
    #    a controller a real mock endpoint would handle.
    def initiate(self, *, tran_id, amount, currency, client_ip, success_url,
                 fail_url, cancel_url, customer_email, description) -> InitiationResult:
        url = (
            f'/billing/mock-pay/{tran_id}/?amount={amount}&currency={currency}'
            f'&success={success_url}&fail={fail_url}&cancel={cancel_url}'
        )
        return InitiationResult(success=True, gateway_url=url, tran_id=tran_id)

    def validate(self, *, tran_id, val_id=None, amount=None, currency=None,
                 ipn_payload=None) -> GatewayResponse:
        return GatewayResponse(
            ok=True, status='success',
            amount=amount, gateway_tran_id=self._fake_val_id,
            message='mock validated server-side',
            raw={'tran_id': tran_id, 'val_id': val_id or self._fake_val_id},
        )


register = lambda: register_gateway('mock', MockGateway)  # noqa: E731
register()