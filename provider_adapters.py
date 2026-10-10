"""Fail-closed interfaces for approved payment and marketplace providers.

These adapters never store card data. Live operations require official merchant approval,
provider credentials, signed webhook validation and separate production review.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from typing import Any


class ProviderNotReady(RuntimeError):
    pass


def usd_amount(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid USD amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("USD amount must be positive and finite")
    return str(amount.quantize(Decimal("0.01")))


@dataclass(frozen=True)
class ProviderReadiness:
    provider: str
    configured: bool
    enabled: bool
    missing: tuple[str, ...]
    message: str


def readiness(provider: str) -> ProviderReadiness:
    specs = {
        "redotpay": ("REDOTPAY_APP_KEY", "REDOTPAY_PRIVATE_KEY_PATH", "REDOTPAY_PLATFORM_PUBLIC_KEY_PATH"),
        "stripe": ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
        "paypal": ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"),
        "amazon_sp_api": ("AMAZON_SP_API_LWA_CLIENT_ID", "AMAZON_SP_API_LWA_CLIENT_SECRET", "AMAZON_SP_API_REFRESH_TOKEN"),
        "aliexpress": ("ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET"),
        "alibaba": ("ALIBABA_APP_KEY", "ALIBABA_APP_SECRET"),
    }
    if provider not in specs:
        raise ValueError("Unknown provider")
    missing = tuple(key for key in specs[provider] if not os.getenv(key, "").strip())
    enabled = os.getenv(f"{provider.upper()}_LIVE_ENABLED", "false").lower() == "true"
    return ProviderReadiness(
        provider=provider,
        configured=not missing,
        enabled=enabled and not missing,
        missing=missing,
        message="Ready for adapter implementation review only; configuration does not prove provider approval.",
    )


class PaymentAdapter:
    """Interface contract; provider-specific methods must implement verified API calls."""
    provider = "abstract"

    def create_checkout(self, *, order_id: str, user_id: str, amount_usd: Any) -> dict[str, Any]:
        raise ProviderNotReady("No live payment adapter is enabled.")

    def verify_webhook(self, *, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        raise ProviderNotReady("No verified webhook adapter is enabled.")

    def reconcile_payment(self, *, provider_payment_id: str) -> dict[str, Any]:
        raise ProviderNotReady("No payment reconciliation adapter is enabled.")


class MarketplaceAdapter:
    """Interface contract for approved read-only research and authorized order APIs."""
    provider = "abstract"

    def search_products(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        raise ProviderNotReady("No approved live catalog connector is enabled.")

    def place_order(self, *, order_id: str, maximum_total_usd: Any) -> dict[str, Any]:
        raise ProviderNotReady("Live purchases are disabled until official access and safety review.")
