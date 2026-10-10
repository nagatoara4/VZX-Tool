"""RedotPay Connect Open API v2: sandbox checkout only.

This module collects payments to the merchant. It is not a card-spending API and
must not be treated as authorization to buy products from Amazon. It deliberately
has no production endpoint and never credits a user's balance from a browser redirect.
"""
from __future__ import annotations

import base64
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

SANDBOX_BASE_URL = "https://acquirersandbox.rp-2023app.com"
ORDER_CREATE_PATH = "/openapi/v2/order/create"


class RedotPayError(RuntimeError):
    """A safe-to-display integration error."""


def money_usd(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid USD amount") from exc
    rounded = amount.quantize(Decimal("0.01"))
    if not amount.is_finite() or rounded < Decimal("0.01") or amount > Decimal("10000"):
        raise ValueError("USD amount must round to at least 0.01 and not exceed 10,000.00")
    return format(rounded, "f")


def _private_key(path: str):
    try:
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    except Exception as exc:
        raise RedotPayError("Could not load RedotPay merchant private key.") from exc
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise RedotPayError("RedotPay signing key must be RSA with at least 2048 bits.")
    return key


def sign_request(method: str, uri: str, app_key: str, timestamp_ms: int, body: str, key_path: str) -> str:
    message = f"{method.upper()} {uri}\n{app_key}.{timestamp_ms}.{body}".encode("utf-8")
    signature = _private_key(key_path).sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def create_sandbox_checkout(
    *,
    user_id: str,
    order_id: str,
    amount_usd: Any,
    product_name: str = "VZX-Tool funding",
    category_code: str = "Z000",
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Create a hosted checkout in sandbox only; never confirms payment."""
    if os.getenv("REDOTPAY_ENV", "sandbox").lower() != "sandbox":
        raise RedotPayError("Live RedotPay checkout is intentionally blocked in this release.")
    app_key = os.getenv("REDOTPAY_APP_KEY", "").strip()
    key_path = os.getenv("REDOTPAY_PRIVATE_KEY_PATH", "").strip()
    key_version = os.getenv("REDOTPAY_KEY_VERSION", "1").strip()
    if not app_key or not key_path:
        raise RedotPayError("Sandbox credentials missing: set REDOTPAY_APP_KEY and REDOTPAY_PRIVATE_KEY_PATH.")
    if not user_id or len(user_id) > 32:
        raise ValueError("user_id must be 1-32 characters")
    if not order_id or not (6 <= len(order_id) <= 32) or not all(c.isalnum() or c in "_-|*" for c in order_id):
        raise ValueError("order_id must be 6-32 characters using letters, digits, _ - | *")
    if not product_name or len(product_name) > 31:
        raise ValueError("product_name must be 1-31 characters")

    amount = money_usd(amount_usd)
    payload = {
        "outerOrderSn": order_id,
        "outerUid": user_id,
        "orderAmount": float(amount),
        "orderCurrency": "USD",
        "env": "WEB",
        "orderDesc": "VZX-Tool sandbox funding",
        "goods": [{
            "goodsType": "02",
            "goodsCategory": category_code,
            "goodsCode": "VZX-FUND",
            "goodsName": product_name,
            "goodsCount": 1,
            "goodsAmount": float(amount),
            "goodsCoin": "USD",
        }],
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = int(time.time() * 1000)
    signature = sign_request("POST", ORDER_CREATE_PATH, app_key, timestamp, body, key_path)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-R-AK": app_key,
        "X-R-TS": str(timestamp),
        "X-R-KEY-VERSION": key_version,
        "X-R-Signature": signature,
    }
    request = Request(SANDBOX_BASE_URL + ORDER_CREATE_PATH, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read(1_000_001)
            if len(response_body) > 1_000_000:
                raise RedotPayError("RedotPay response exceeded the allowed size.")
            result = json.loads(response_body.decode("utf-8"))
    except HTTPError as exc:
        raise RedotPayError(f"RedotPay sandbox returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise RedotPayError("RedotPay sandbox is unreachable or timed out.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RedotPayError("RedotPay sandbox returned invalid JSON.") from exc

    if not isinstance(result, dict) or result.get("code") != "SUCCESS":
        code = result.get("code", "unknown") if isinstance(result, dict) else "invalid-response"
        raise RedotPayError(f"RedotPay sandbox did not create the checkout (code={code}).")
    data = result.get("data")
    if not isinstance(data, dict):
        raise RedotPayError("RedotPay response omitted checkout data.")
    checkout_url = data.get("webUrl") or data.get("h5Url")
    if not isinstance(checkout_url, str) or not checkout_url.startswith("https://"):
        raise RedotPayError("RedotPay response did not include a valid HTTPS checkout URL.")
    return {
        "provider": "redotpay",
        "environment": "sandbox",
        "status": "pending_payment",
        "user_id": user_id,
        "order_id": order_id,
        "amount_usd": amount,
        "provider_order_id": data.get("orderSn"),
        "checkout_url": checkout_url,
        "payment_confirmed": False,
        "ledger_credit_allowed": False,
    }


def verify_webhook_signature(*, raw_body: bytes, app_key: str, timestamp: str, signature_b64: str, key_version: str, public_key_path: str) -> bool:
    """Verify a callback with the platform public key for the matching environment/version."""
    if not raw_body or len(raw_body) > 1_000_000:
        return False
    if not timestamp.isdigit() or not key_version.isdigit() or not signature_b64:
        return False
    if abs(int(time.time() * 1000) - int(timestamp)) > 5 * 60 * 1000:
        return False
    try:
        public_key = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
        if not isinstance(public_key, rsa.RSAPublicKey):
            return False
        signature = base64.b64decode(signature_b64, validate=True)
        signed = f"{app_key}.{timestamp}.".encode("utf-8") + raw_body
        public_key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False
