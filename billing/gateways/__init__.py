"""Gateway adapter registry. Importing this module registers adapters."""
from billing.gateways.base import (
    InitiationResult, PaymentGateway, GatewayResponse,
    available_gateways, get_gateway, register_gateway,
)
from billing.gateways import mock  # noqa: F401
from billing.gateways import sslcommerz  # noqa: F401

# Alias kept for back-compat with earlier scaffold names
PaymentGatewayABC = PaymentGateway