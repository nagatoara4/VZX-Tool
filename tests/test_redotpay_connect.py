import base64
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from redotpay_connect import RedotPayError, create_sandbox_checkout, money_usd, sign_request, verify_webhook_signature


def test_money_usd_validation():
    assert money_usd("12.30") == "12.30"
    with pytest.raises(ValueError):
        money_usd("0.001")
    with pytest.raises(ValueError):
        money_usd("10000.01")
    with pytest.raises(ValueError):
        money_usd("-1")
    with pytest.raises(ValueError):
        money_usd("NaN")


def test_live_environment_is_blocked(monkeypatch):
    monkeypatch.setenv("REDOTPAY_ENV", "production")
    monkeypatch.setenv("REDOTPAY_APP_KEY", "not-a-real-key")
    with pytest.raises(RedotPayError, match="intentionally blocked"):
        create_sandbox_checkout(user_id="user-1", order_id="ORD123456", amount_usd="10")


def test_checkout_requires_credentials(monkeypatch):
    monkeypatch.setenv("REDOTPAY_ENV", "sandbox")
    monkeypatch.delenv("REDOTPAY_APP_KEY", raising=False)
    monkeypatch.delenv("REDOTPAY_PRIVATE_KEY_PATH", raising=False)
    with pytest.raises(RedotPayError, match="credentials missing"):
        create_sandbox_checkout(user_id="user-1", order_id="ORD123456", amount_usd="10")


def test_signing_and_webhook_verification(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    public_path.write_bytes(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    timestamp = str(time.time_ns() // 1_000_000)
    body = b'{"event":"test"}'
    signed = f"app-key.{timestamp}.".encode() + body
    signature = private_key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    encoded = base64.b64encode(signature).decode()
    assert verify_webhook_signature(raw_body=body, app_key="app-key", timestamp=timestamp,
        signature_b64=encoded, key_version="1", public_key_path=str(public_path))
    assert not verify_webhook_signature(raw_body=body + b" ", app_key="app-key", timestamp=timestamp,
        signature_b64=encoded, key_version="1", public_key_path=str(public_path))


def test_sign_request_produces_base64_signature(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "private.pem"
    key_path.write_bytes(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    signature = sign_request("POST", "/openapi/v2/order/create", "app", 123, '{"a":1}', str(key_path))
    assert base64.b64decode(signature)
