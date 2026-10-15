"""Gateway abstraction.

``billing.gateways`` exposes a base :class:`PaymentGateway` ABC. Each adapter
implements ``initiate`` (build the gateway redirect URL) and ``validate``
(server-side validation of a webhook/redirect, comparing the amount and our
``tran_id`` against the gateway). Views never import a specific adapter; they
ask the registry for the named gateway.

SSLCommerz is the first live adapter; mock lets the rest of the system (and the
tests) run without network access.
"""
from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional


@dataclass
class GatewayResponse:
    ok: bool
    status: str  # 'success' | 'failed' | 'pending'
    amount: Optional[Decimal] = None
    gateway_tran_id: Optional[str] = None
    message: str = ''
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InitiationResult:
    """What `initiate` returns: a URL to redirect to and our tran_id."""
    success: bool
    gateway_url: Optional[str] = None
    tran_id: Optional[str] = None
    message: str = ''
    raw: Dict[str, Any] = field(default_factory=dict)


VALIDATION_AMOUNT_TOLERANCE = Decimal('0.005')


class PaymentGateway(abc.ABC):
    """Abstract payment gateway.

    Adapters are stateless. Instantiate per-request with the gateway
    credentials pulled from the environment / ``SiteConfiguration``.
    """

    name: str = 'base'

    def __init__(self, *, sandbox: bool = True, store_id: str = '',
                 store_password: str = '', **extra):
        self.sandbox = sandbox
        self.store_id = store_id
        self.store_password = store_password
        self.extra = extra

    # ------------------------------------------------------------------ public
    @abc.abstractmethod
    def initiate(self, *, tran_id: str, amount: Decimal, currency: str,
                 client_ip: str, success_url: str, fail_url: str,
                 cancel_url: str, customer_email: str, description: str) -> InitiationResult:
        """Build a gateway session and return a redirect URL."""

    @abc.abstractmethod
    def validate(self, *, tran_id: str, val_id: Optional[str] = None,
                 amount: Optional[Decimal] = None,
                 currency: Optional[str] = None,
                 ipn_payload: Optional[Dict[str, Any]] = None) -> GatewayResponse:
        """Server-side validation. MUST call the gateway's validation API;
        never trust IPN/redirect parameters."""

    # ---------------------------------------------------------------- helpers
    def is_validation_ok(self, *, trusted_amount: Decimal, response: GatewayResponse) -> bool:
        """Compare the gateway's reported amount against what we sent
        (within a tolerance). Replay/tamper protection: the amount cell must
        match our own ledger, not a path-supplied value."""
        if not response.ok or response.amount is None:
            return False
        if (abs(response.amount - trusted_amount) > VALIDATION_AMOUNT_TOLERANCE):
            return False
        return True


# ------------------------------ registry
_GATEWAYS = {}


def register_gateway(name, factory):
    _GATEWAYS[name] = factory


def get_gateway(name, **credentials):
    if name not in _GATEWAYS:
        raise ValueError(f'Unknown gateway: {name!r}. Available: {sorted(_GATEWAYS)}')
    return _GATEWAYS[name](**credentials)


def available_gateways():
    return sorted(_GATEWAYS)


def _lazy_register_defaults():
    from billing.gateways import sslcommerz, mock  # noqa: F401