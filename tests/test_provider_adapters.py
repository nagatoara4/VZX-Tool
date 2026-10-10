import pytest
from provider_adapters import ProviderNotReady, PaymentAdapter, MarketplaceAdapter, readiness, usd_amount


def test_usd_amount_decimal_validation():
    assert usd_amount("12.345") == "12.34"
    with pytest.raises(ValueError):
        usd_amount("-1")


def test_payment_adapter_fails_closed():
    with pytest.raises(ProviderNotReady):
        PaymentAdapter().create_checkout(order_id="order123", user_id="user123", amount_usd=10)


def test_marketplace_purchase_fails_closed():
    with pytest.raises(ProviderNotReady):
        MarketplaceAdapter().place_order(order_id="order123", maximum_total_usd=10)


def test_provider_readiness_does_not_claim_live_approval(monkeypatch):
    for key in ("REDOTPAY_APP_KEY", "REDOTPAY_PRIVATE_KEY_PATH", "REDOTPAY_PLATFORM_PUBLIC_KEY_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("REDOTPAY_LIVE_ENABLED", raising=False)
    status = readiness("redotpay")
    assert status.configured is False
    assert status.enabled is False
    assert status.missing
