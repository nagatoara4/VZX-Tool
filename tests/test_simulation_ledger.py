from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["COMMERCE_DB_PATH"] = os.path.join(tempfile.gettempdir(), f"vzx-simulation-tests-{os.getpid()}.db")
os.environ["AUTH_SECRET"] = "simulation-test-secret-longer-than-thirty-two-characters"

from fastapi.testclient import TestClient
from app import app
from simulation_ledger import init_simulation_db

init_simulation_db()
client = TestClient(app)


def login_headers(email: str, name: str) -> dict[str, str]:
    registered = client.post("/api/v1/auth/register", json={
        "email": email, "password": "StrongTestPass123", "display_name": name
    })
    assert registered.status_code in (201, 409), registered.text
    logged = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongTestPass123"})
    assert logged.status_code == 200, logged.text
    return {"Authorization": "Bearer " + logged.json()["access_token"]}


def test_simulation_order_lifecycle_and_profit():
    headers = login_headers("sim-lifecycle@example.com", "Sim Lifecycle")
    funded = client.post("/api/v1/simulation/cash", headers=headers, json={
        "amount_usd": "100.00", "reference": "sim-seed-life-001"
    })
    assert funded.status_code == 201, funded.text
    assert funded.json()["available_balance_usd"] == 100.0
    order = client.post("/api/v1/simulation/orders", headers=headers, json={
        "product_name": "Desk lamp", "quantity": 2, "product_cost_usd": "20.00",
        "shipping_budget_usd": "10.00", "fee_budget_usd": "5.00", "idempotency_key": "sim-order-life-001"
    })
    assert order.status_code == 201, order.text
    assert order.json()["reserved_usd"] == 55.0
    assert order.json()["available_balance_usd"] == 45.0
    repeated = client.post("/api/v1/simulation/orders", headers=headers, json={
        "product_name": "Desk lamp", "quantity": 2, "product_cost_usd": "20.00",
        "shipping_budget_usd": "10.00", "fee_budget_usd": "5.00", "idempotency_key": "sim-order-life-001"
    })
    assert repeated.status_code == 201
    assert repeated.json()["duplicate"] is True
    settled = client.post("/api/v1/simulation/orders/" + order.json()["id"] + "/settle", headers=headers, json={
        "sale_price_usd": "80.00", "actual_shipping_usd": "8.00", "actual_fees_usd": "4.00"
    })
    assert settled.status_code == 200, settled.text
    assert settled.json()["total_cost_usd"] == 52.0
    assert settled.json()["net_profit_usd"] == 28.0
    again = client.post("/api/v1/simulation/orders/" + order.json()["id"] + "/settle", headers=headers, json={
        "sale_price_usd": "80.00", "actual_shipping_usd": "8.00", "actual_fees_usd": "4.00"
    })
    assert again.json()["duplicate"] is True
    account = client.get("/api/v1/simulation/account", headers=headers).json()
    assert account["realized_net_profit_usd"] == 28.0
    assert account["available_balance_usd"] == 128.0
    assert account["mode"] == "simulation_only"


def test_simulated_cash_isolated_per_user():
    a = login_headers("sim-isolation-a@example.com", "Sim A")
    b = login_headers("sim-isolation-b@example.com", "Sim B")
    client.post("/api/v1/simulation/cash", headers=a, json={"amount_usd": "40", "reference": "sim-seed-user-a-01"})
    account_b = client.get("/api/v1/simulation/account", headers=b)
    assert account_b.status_code == 200
    assert account_b.json()["available_balance_usd"] == 0.0
    hidden = client.post("/api/v1/simulation/orders/sim-order-life-001/settle", headers=b, json={
        "sale_price_usd": "80", "actual_shipping_usd": "8", "actual_fees_usd": "4"
    })
    assert hidden.status_code == 404


def test_pending_real_funding_does_not_create_simulation_cash():
    headers = login_headers("sim-pending-funding@example.com", "Pending")
    pending = client.post("/api/v1/budget", headers=headers, json={"amount": 500})
    assert pending.status_code == 200
    account = client.get("/api/v1/simulation/account", headers=headers).json()
    assert account["available_balance_usd"] == 0.0
    order = client.post("/api/v1/simulation/orders", headers=headers, json={
        "product_name": "Keyboard", "quantity": 1, "product_cost_usd": "10",
        "shipping_budget_usd": "1", "fee_budget_usd": "1", "idempotency_key": "sim-no-funds-001"
    })
    assert order.status_code == 409


def test_duplicate_cash_reference_cannot_be_reused_for_different_amount():
    headers = login_headers("sim-idempotency@example.com", "Idempotency")
    first = client.post("/api/v1/simulation/cash", headers=headers, json={
        "amount_usd": "25", "reference": "sim-seed-repeat-001"
    })
    assert first.status_code == 201
    duplicate = client.post("/api/v1/simulation/cash", headers=headers, json={
        "amount_usd": "25", "reference": "sim-seed-repeat-001"
    })
    assert duplicate.json()["status"] == "duplicate"
    conflict = client.post("/api/v1/simulation/cash", headers=headers, json={
        "amount_usd": "250", "reference": "sim-seed-repeat-001"
    })
    assert conflict.status_code == 409
