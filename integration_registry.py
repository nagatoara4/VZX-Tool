"""Integration registry: readiness diagnostics only; no provider can move money in this module."""
from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationStatus:
    provider: str
    category: str
    configured: bool
    live_enabled: bool
    missing_variables: tuple[str, ...]
    note: str


PROVIDERS = {
    "stripe": ("payments", ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")),
    "paypal": ("payments", ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID")),
    "amazon_sp_api": ("marketplace", ("AMAZON_SP_API_LWA_CLIENT_ID", "AMAZON_SP_API_LWA_CLIENT_SECRET", "AMAZON_SP_API_REFRESH_TOKEN")),
    "aliexpress": ("supplier", ("ALIEXPRESS_APP_KEY", "ALIEXPRESS_APP_SECRET")),
    "alibaba": ("supplier", ("ALIBABA_APP_KEY", "ALIBABA_APP_SECRET")),
}


def integration_status() -> list[dict[str, object]]:
    """Credentials indicate configuration only, never authorization or production readiness."""
    result = []
    for provider, (category, variables) in PROVIDERS.items():
        missing = tuple(name for name in variables if not os.getenv(name, "").strip())
        result.append({
            "provider": provider,
            "category": category,
            "configured": not missing,
            "live_enabled": False,
            "missing_variables": list(missing),
            "note": "Readiness only; implement and verify official OAuth/webhooks/API permissions before live use.",
        })
    return result
