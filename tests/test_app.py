import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Isolated database and test-only signing secret; never use these values in production.
os.environ["COMMERCE_DB_PATH"] = os.path.join(tempfile.gettempdir(), f"commerce-os-tests-{os.getpid()}.db")
os.environ["ADMIN_API_KEY"] = "test-owner-secret"
os.environ["AUTH_SECRET"] = "test-only-secret-longer-than-thirty-two-characters-000"
os.environ["DEFAULT_ACTION_CAP"] = "25"
os.environ["EXECUTION_MODE"] = "simulation"

from fastapi.testclient import TestClient
from app import app, init_db
from platform_api import init_platform_db
from agent_worker import init_queue

init_db()
init_platform_db()
init_queue()
client = TestClient(app)
HEADERS = {"X-Admin-Key": "test-owner-secret"}


def register_and_login(email, display_name):
    registered = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "StrongTestPass123",
        "display_name": display_name
    })
    assert registered.status_code == 201, registered.text
    logged_in = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "StrongTestPass123"
    })
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": "Bearer " + logged_in.json()["access_token"]}


def test_health_and_policy_are_simulation_only():
    assert client.get("/health").status_code == 200
    policy = client.get("/policy").json()
    assert policy["automatic_money_movement"] is False
    assert policy["execution_mode"] == "simulation"
    assert policy["agent_policy"]["financial_execution"] is False


def test_product_scoring_rejects_high_compliance_risk():
    payload = {
        "name": "Sample product",
        "demand": 80,
        "competition": 30,
        "margin": 70,
        "supplier_reliability": 80,
        "fulfilment_fit": 75,
        "compliance_risk": 90,
    }
    result = client.post("/products/score", json=payload)
    assert result.status_code == 200
    assert result.json()["verdict"] == "reject_or_manual_compliance_review"


def test_owner_endpoint_requires_key():
    response = client.post("/owner/fund", json={"amount": 200})
    assert response.status_code in (401, 503)


def test_funding_and_proposal_limits():
    funded = client.post("/owner/fund", headers=HEADERS, json={"amount": 200, "note": "test cycle"})
    assert funded.status_code == 200
    proposal = client.post("/proposals", headers=HEADERS, json={
        "kind": "sample_purchase",
        "amount": 30,
        "rationale": "This proposal exceeds the configured per-action cap.",
        "idempotency_key": "sample-test-key-0001"
    })
    assert proposal.status_code == 409


def test_multi_user_accounts_and_ledgers_are_isolated():
    headers_a = register_and_login("alpha@example.com", "Alpha")
    headers_b = register_and_login("bravo@example.com", "Bravo")
    budget_a = client.post("/api/v1/budget", headers=headers_a, json={"amount": 125})
    budget_b = client.post("/api/v1/budget", headers=headers_b, json={"amount": 75})
    assert budget_a.status_code == 200
    assert budget_b.status_code == 200
    assert budget_a.json()["status"] == "pending_payment"
    assert budget_a.json()["payment_url"] is None
    account_a = client.get("/api/v1/account", headers=headers_a).json()
    account_b = client.get("/api/v1/account", headers=headers_b).json()
    assert account_a["user_id"] != account_b["user_id"]
    assert account_a["cycles"][0]["initial_capital"] == 125
    assert account_b["cycles"][0]["initial_capital"] == 75
    ledger_a = client.get("/api/v1/ledger", headers=headers_a).json()["entries"]
    ledger_b = client.get("/api/v1/ledger", headers=headers_b).json()["entries"]
    assert len(ledger_a) == len(ledger_b) == 1
    assert ledger_a[0]["cycle_id"] != ledger_b[0]["cycle_id"]
    assert ledger_a[0]["id"] != ledger_b[0]["id"]
    assert ledger_a[0]["status"] == "pending_payment"
    assert account_a["recorded_balance"] == 0


def test_auth_required_for_private_account_data():
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/account").status_code == 401


def test_declared_budget_is_not_spendable_cash():
    headers = register_and_login("charlie@example.com", "Charlie")
    client.post("/api/v1/budget", headers=headers, json={"amount": 200})
    response = client.post("/api/v1/proposals", headers=headers, json={
        "kind": "sample_purchase",
        "amount": 10,
        "rationale": "This must be blocked until a payment provider confirms funds.",
        "idempotency_key": "pending-payment-proposal-01"
    })
    assert response.status_code == 409
    assert "confirmed available cash" in response.json()["detail"]

def test_agent_task_queue_is_user_scoped_and_does_not_claim_execution():
    headers_a = register_and_login("taskalpha@example.com", "Task Alpha")
    headers_b = register_and_login("taskbravo@example.com", "Task Bravo")
    created = client.post("/api/v1/tasks", headers=headers_a, json={
        "task_type": "daily_report",
        "payload": {"period": "today"}
    })
    assert created.status_code == 202
    task = created.json()
    assert task["status"] == "queued"
    assert task["execution_status"] == "queued_only"
    own = client.get(f"/api/v1/tasks/{task['id']}", headers=headers_a)
    other = client.get(f"/api/v1/tasks/{task['id']}", headers=headers_b)
    assert own.status_code == 200
    assert own.json()["payload"] == {"period": "today"}
    assert other.status_code == 404



def test_opportunity_analysis_api_ranks_candidates_without_executing():
    payload = {
        "available_budget": 100,
        "max_order_spend": 50,
        "candidates": [{
            "product_id": "api-test-product",
            "unit_cost": "10",
            "shipping_per_unit": "2",
            "marketplace_fee_per_unit": "3",
            "tax_per_unit": "1",
            "expected_sale_price": "30",
            "units": 2,
            "demand_score": 90,
            "competition_score": 20,
            "supplier_reliability": 90,
            "compliance_risk": 10
        }]
    }
    response = client.post("/agent/analyze", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["currency"] == "USD"
    assert data["execution_enabled"] is False
    assert data["ranked_opportunities"][0]["expected_profit_total"] == "28.00"


def test_worker_processes_profitability_task_as_analysis_only():
    headers = register_and_login("worker-analysis@example.com", "Worker Analysis")
    queued = client.post("/api/v1/tasks", headers=headers, json={
        "task_type": "profitability_analysis",
        "payload": {
            "available_budget": 100,
            "max_order_spend": 50,
            "candidates": [{
                "product_id": "worker-test-product",
                "unit_cost": 10,
                "shipping_per_unit": 2,
                "marketplace_fee_per_unit": 3,
                "tax_per_unit": 1,
                "expected_sale_price": 30,
                "units": 2,
                "demand_score": 90,
                "competition_score": 20,
                "supplier_reliability": 90,
                "compliance_risk": 10
            }]
        }
    })
    assert queued.status_code == 202
    # Earlier tests may have left queue-only reporting tasks; drain a bounded number
    # of jobs until this exact task has been processed.
    task_id = queued.json()["id"]
    status = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    for _ in range(30):
        if status.json()["status"] != "queued":
            break
        ran = client.post("/agent/worker/run-once", headers=HEADERS)
        assert ran.status_code == 200, ran.text
        status = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["result"]["execution"] == "disabled"


def test_profit_alert_cannot_claim_unreconciled_profit():
    from agent_engine import verified_profit_alert
    import pytest
    with pytest.raises(ValueError):
        verified_profit_alert(amount=10, order_id="pending-1", payment_settled=False, costs_reconciled=False)


def test_audit_log_requires_owner_key():
    assert client.get("/audit").status_code in (401, 503)
    assert client.get("/audit", headers=HEADERS).status_code == 200
