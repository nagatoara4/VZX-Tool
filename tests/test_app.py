import os
import tempfile

os.environ["COMMERCE_DB_PATH"] = os.path.join(tempfile.gettempdir(), "commerce-os-tests.db")
os.environ["ADMIN_API_KEY"] = "test-owner-secret"
os.environ["DEFAULT_ACTION_CAP"] = "25"

from fastapi.testclient import TestClient
from app import app, init_db

init_db()
client = TestClient(app)
HEADERS = {"X-Admin-Key": "test-owner-secret"}


def test_health_and_policy_are_simulation_only():
    assert client.get("/health").status_code == 200
    policy = client.get("/policy").json()
    assert policy["automatic_money_movement"] is False
    assert policy["execution_mode"] == "simulation"


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
