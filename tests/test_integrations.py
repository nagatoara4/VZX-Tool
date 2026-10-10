import os
import pytest
from commerce_integrations import IntegrationDisabled, create_redotpay_checkout
from amazon_sp_api import AmazonIntegrationDisabled, search_catalog


def test_redotpay_checkout_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REDOTPAY_ENABLE_CHECKOUT", raising=False)
    monkeypatch.delenv("ENABLE_CUSTOMER_BALANCE_CREDIT", raising=False)
    with pytest.raises(IntegrationDisabled):
        create_redotpay_checkout(
            order_id="VZXORDER001", user_id="user123", amount="25.00",
            description="Test order", redirect_url="https://example.com/return"
        )


def test_redotpay_rejects_http_redirect(monkeypatch):
    monkeypatch.setenv("REDOTPAY_ENABLE_CHECKOUT", "true")
    monkeypatch.setenv("ENABLE_CUSTOMER_BALANCE_CREDIT", "true")
    monkeypatch.setenv("REDOTPAY_APP_KEY", "test")
    with pytest.raises(ValueError):
        create_redotpay_checkout(
            order_id="VZXORDER001", user_id="user123", amount="25.00",
            description="Test order", redirect_url="http://example.com/return"
        )


def test_amazon_read_only_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AMAZON_SP_API_ENABLE_READS", raising=False)
    with pytest.raises(AmazonIntegrationDisabled):
        search_catalog("wireless charger")
