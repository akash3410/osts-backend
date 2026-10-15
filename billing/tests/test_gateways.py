"""Tests for the gateway abstraction."""
from decimal import Decimal

import pytest

from billing.gateways import available_gateways, get_gateway
from billing.gateways.mock import MockGateway
from billing.gateways.sslcommerz import SslCommerzGateway


pytestmark = pytest.mark.django_db


class TestRegistry:
    def test_mock_and_sslcommerz_registered(self):
        assert 'mock' in available_gateways()
        assert 'sslcommerz' in available_gateways()

    def test_get_mock(self):
        gw = get_gateway('mock')
        assert isinstance(gw, MockGateway)

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            get_gateway('does-not-exist')


class TestMockGateway:
    def test_initiate_returns_gateway_url(self):
        gw = MockGateway()
        res = gw.initiate(tran_id='abc', amount=Decimal('10.00'), currency='BDT',
                          client_ip='127.0.0.1', success_url='s', fail_url='f',
                          cancel_url='c', customer_email='x@y.com', description='desc')
        assert res.success
        assert res.gateway_url is not None
        assert res.tran_id == 'abc'

    def test_validate_ok_amount(self):
        gw = MockGateway()
        res = gw.validate(tran_id='abc', amount=Decimal('10.00'), currency='BDT')
        assert res.ok and res.status == 'success'
        assert res.amount == Decimal('10.00')

    def test_is_validation_ok_amount_mismatch_rejected(self):
        gw = MockGateway()
        res = gw.validate(tran_id='abc', amount=Decimal('5.00'))
        # is_validation_ok compares against the TRUSTED amount (10.00), not
        # the gateway-reported 5.00.
        assert not gw.is_validation_ok(trusted_amount=Decimal('10.00'), response=res)


class TestSslCommerzGateway:
    def test_sandbox_base(self):
        gw = SslCommerzGateway(sandbox=True, store_id='X', store_password='Y')
        assert gw._base().startswith('https://sandbox.')

    def test_prod_base(self):
        gw = SslCommerzGateway(sandbox=False, store_id='X', store_password='Y')
        assert gw._base().startswith('https://securepay.')

    def test_initiate_without_credentials_returns_failed_or_session(self):
        # Adapter must not hard-crash — returns a failed InitiationResult
        gw = SslCommerzGateway(sandbox=True, store_id='', store_password='')
        res = gw.initiate(tran_id='t', amount=Decimal('10.00'), currency='BDT',
                          client_ip='127.0.0.1', success_url='s', fail_url='f',
                          cancel_url='c', customer_email='x', description='d')
        # Without creds it'll fail OR (if network blocked) report unreachable.
        # We just assert the shape is well-formed — no exceptions.
        assert isinstance(res.success, bool)
        assert isinstance(res.message, str)


class TestIdempotencyCompare:
    def test_amount_mismatch_rejected_helper(self):
        gw = MockGateway()
        res = gw.validate(tran_id='x', amount=Decimal('10.00'))
        # Even if gateway reports 10, if our trusted amount is 9.99 it fails.
        assert not gw.is_validation_ok(trusted_amount=Decimal('9.99'), response=res)