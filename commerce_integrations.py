"""Legacy compatibility facade for older integration tests and callers.

Live checkout remains disabled. RedotPay Connect in redotpay_connect.py is a
merchant collection flow and this facade never credits user balances.
"""
from __future__ import annotations
import os
from urllib.parse import urlparse


class IntegrationDisabled(RuntimeError):
    pass


def create_redotpay_checkout(*, order_id: str, user_id: str, amount: str,
                             description: str, redirect_url: str) -> dict:
    parsed = urlparse(redirect_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("redirect_url must be an absolute HTTPS URL")
    if os.getenv("REDOTPAY_ENABLE_CHECKOUT", "false").lower() != "true":
        raise IntegrationDisabled("RedotPay checkout is disabled; use the sandbox-only Connect client.")
    # Do not pretend the old generic flag is enough to enable a live provider call.
    raise IntegrationDisabled("This compatibility facade has no live checkout implementation; use the approved sandbox endpoint.")
