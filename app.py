from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from platform_api import router as platform_router, init_platform_db
from agent_worker import init_queue, execution_policy

load_dotenv()

APP_NAME = "Autonomous Commerce OS"
DB_PATH = os.getenv("COMMERCE_DB_PATH", "commerce.db")
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "simulation").lower()
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
LOSS_LIMIT_PCT = float(os.getenv("LOSS_LIMIT_PCT", "0.30"))
REINVESTMENT_PCT = float(os.getenv("REINVESTMENT_PCT", "0.80"))
DEFAULT_ACTION_CAP = float(os.getenv("DEFAULT_ACTION_CAP", "25.00"))

app = FastAPI(title=APP_NAME, version="0.2.0", description="Multi-user risk-controlled commerce control plane. Payment and marketplace execution remain disabled until verified integrations are configured.")
app.include_router(platform_router)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cycles (
            id TEXT PRIMARY KEY, initial_capital REAL NOT NULL,
            loss_limit REAL NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS ledger (
            id TEXT PRIMARY KEY, cycle_id TEXT, kind TEXT NOT NULL,
            amount REAL NOT NULL, note TEXT NOT NULL, cleared INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, reference TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, amount REAL NOT NULL,
            status TEXT NOT NULL, rationale TEXT NOT NULL, idempotency_key TEXT UNIQUE,
            created_at TEXT NOT NULL, resolved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit (
            id TEXT PRIMARY KEY, event TEXT NOT NULL, detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()
    init_platform_db()
    init_queue()


def audit(event: str, detail: dict[str, Any]) -> None:
    with closing(db()) as conn:
        conn.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), event, json.dumps(detail, sort_keys=True), now()))
        conn.commit()


def require_owner(x_admin_key: str | None) -> None:
    # Safe local-only default: if no key is configured, mutating endpoints are disabled.
    if not ADMIN_API_KEY:
        raise HTTPException(503, "Owner actions disabled: set ADMIN_API_KEY in the environment.")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(401, "Invalid owner API key.")


def current_cycle(conn: sqlite3.Connection) -> sqlite3.Row | None:
    # Always surface the latest cycle, including halted cycles, so a stop cannot be bypassed implicitly.
    return conn.execute("SELECT * FROM cycles ORDER BY created_at DESC LIMIT 1").fetchone()


def ledger_totals(conn: sqlite3.Connection, cycle_id: str | None = None) -> dict[str, float]:
    where = " WHERE cleared=1"
    params: tuple[Any, ...] = ()
    if cycle_id:
        where += " AND cycle_id=?"
        params = (cycle_id,)
    rows = conn.execute("SELECT kind, amount FROM ledger" + where, params).fetchall()
    # Deposits and realized income increase cash; expenses, purchases and liabilities reduce it.
    positive = {"deposit", "realized_income", "refund_received"}
    negative = {"expense", "purchase", "refund_paid", "liability_reserved"}
    cash = 0.0
    realized_income = 0.0
    expenses = 0.0
    for row in rows:
        kind, amount = row["kind"], float(row["amount"])
        if kind in positive:
            cash += amount
        elif kind in negative:
            cash -= amount
        if kind in {"realized_income", "refund_received"}:
            realized_income += amount
        if kind in {"expense", "purchase", "refund_paid"}:
            expenses += amount
    return {"cash_available": round(cash, 2), "realized_income": round(realized_income, 2), "expenses": round(expenses, 2)}


def cycle_loss(conn: sqlite3.Connection, cycle: sqlite3.Row) -> float:
    # Loss is capital drawdown from cycle deposits after deducting available cash.
    totals = ledger_totals(conn, cycle["id"])
    return max(0.0, round(float(cycle["initial_capital"]) - totals["cash_available"], 2))


class FundingRequest(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    note: str = Field(default="Owner funding", min_length=1, max_length=240)
    start_new_cycle: bool = False


class LedgerRequest(BaseModel):
    kind: Literal["expense", "purchase", "realized_income", "refund_received", "refund_paid", "liability_reserved"]
    amount: float = Field(gt=0, le=1_000_000)
    note: str = Field(min_length=1, max_length=240)
    cleared: bool = True
    reference: str | None = Field(default=None, max_length=120)


class ProductInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    demand: float = Field(ge=0, le=100)
    competition: float = Field(ge=0, le=100, description="100 means very crowded")
    margin: float = Field(ge=0, le=100)
    supplier_reliability: float = Field(ge=0, le=100)
    fulfilment_fit: float = Field(ge=0, le=100)
    compliance_risk: float = Field(ge=0, le=100, description="100 means very high risk")
    evidence_url: str | None = Field(default=None, max_length=500)
    evidence_checked_at: str | None = Field(default=None, max_length=80)

    @field_validator("evidence_url")
    @classmethod
    def validate_evidence_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("evidence_url must be http(s)")
        return value


class ProposalRequest(BaseModel):
    kind: Literal["sample_purchase", "inventory_purchase", "advertising", "tooling", "other"]
    amount: float = Field(gt=0, le=1_000_000)
    rationale: str = Field(min_length=10, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


@app.get("/")
def root() -> dict[str, Any]:
    return {"name": APP_NAME, "version": "0.1.0", "mode": EXECUTION_MODE, "status": "running", "external_execution_connected": False}


@app.get("/ui", include_in_schema=False)
def dashboard_ui() -> FileResponse:
    """Serve the dashboard from the same origin as the API to avoid file:// CORS issues."""
    return FileResponse(Path(__file__).with_name("dashboard.html"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": now()}


@app.get("/dashboard")
def dashboard() -> dict[str, Any]:
    with closing(db()) as conn:
        cycle = current_cycle(conn)
        totals = ledger_totals(conn, cycle["id"] if cycle else None)
        if not cycle:
            return {"cycle": None, "totals": totals, "loss_limit_pct": LOSS_LIMIT_PCT, "reinvestment_pct": REINVESTMENT_PCT, "message": "Owner must fund a cycle before financial actions."}
        loss = cycle_loss(conn, cycle)
        pending = conn.execute("SELECT COUNT(*) AS n FROM proposals WHERE status='pending'").fetchone()["n"]
        return {
            "cycle": {"id": cycle["id"], "initial_capital": cycle["initial_capital"], "loss_limit": cycle["loss_limit"], "loss_used": loss, "loss_remaining": round(max(0, cycle["loss_limit"] - loss), 2), "status": cycle["status"]},
            "totals": totals,
            "loss_limit_pct": LOSS_LIMIT_PCT,
            "reinvestment_pct": REINVESTMENT_PCT,
            "pending_proposals": pending,
            "execution_mode": EXECUTION_MODE,
        }


@app.post("/owner/fund")
def fund(req: FundingRequest, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_owner(x_admin_key)
    with closing(db()) as conn:
        cycle = current_cycle(conn)
        if cycle and req.start_new_cycle:
            conn.execute("UPDATE cycles SET status='closed' WHERE id=?", (cycle["id"],))
            cycle = None
        elif cycle and cycle["status"] == "halted":
            raise HTTPException(409, "Cycle is halted. Explicitly request start_new_cycle after owner review.")
        if not cycle:
            cycle_id = str(uuid.uuid4())
            conn.execute("INSERT INTO cycles VALUES (?, ?, ?, ?, 'active')", (cycle_id, req.amount, round(req.amount * LOSS_LIMIT_PCT, 2), now()))
        else:
            cycle_id = cycle["id"]
        ref = "fund-" + str(uuid.uuid4())
        conn.execute("INSERT INTO ledger VALUES (?, ?, 'deposit', ?, ?, 1, ?, ?)", (str(uuid.uuid4()), cycle_id, req.amount, req.note, now(), ref))
        conn.commit()
    audit("owner_funded_cycle", {"cycle_id": cycle_id, "amount": req.amount, "start_new_cycle": req.start_new_cycle})
    return {"ok": True, "cycle_id": cycle_id, "amount_recorded": req.amount, "note": "This records an owner-declared deposit; it does not move money between accounts."}


@app.post("/owner/ledger")
def add_ledger(req: LedgerRequest, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_owner(x_admin_key)
    with closing(db()) as conn:
        cycle = current_cycle(conn)
        if not cycle:
            raise HTTPException(409, "Fund a cycle first.")
        if req.reference and conn.execute("SELECT 1 FROM ledger WHERE reference=?", (req.reference,)).fetchone():
            raise HTTPException(409, "Duplicate ledger reference.")
        totals = ledger_totals(conn, cycle["id"])
        if req.kind in {"expense", "purchase", "refund_paid", "liability_reserved"} and req.amount > totals["cash_available"]:
            raise HTTPException(409, "Insufficient available cash.")
        conn.execute("INSERT INTO ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), cycle["id"], req.kind, req.amount, req.note, int(req.cleared), now(), req.reference))
        updated = ledger_totals(conn, cycle["id"])
        loss = cycle_loss(conn, cycle)
        if loss >= cycle["loss_limit"]:
            conn.execute("UPDATE cycles SET status='halted' WHERE id=?", (cycle["id"],))
        conn.commit()
    audit("ledger_entry", {"kind": req.kind, "amount": req.amount, "loss": loss})
    return {"ok": True, "totals": updated, "loss_used": loss, "halted": loss >= cycle["loss_limit"]}


@app.post("/products/score")
def score_product(product: ProductInput) -> dict[str, Any]:
    # Competition and compliance risk are inverted: lower risk/crowding is better.
    weighted = (
        product.demand * 0.25
        + (100 - product.competition) * 0.15
        + product.margin * 0.25
        + product.supplier_reliability * 0.15
        + product.fulfilment_fit * 0.10
        + (100 - product.compliance_risk) * 0.10
    )
    score = round(weighted, 1)
    if product.compliance_risk >= 75:
        verdict = "reject_or_manual_compliance_review"
    elif score >= 75:
        verdict = "research_further"
    elif score >= 60:
        verdict = "watchlist"
    else:
        verdict = "reject"
    return {"product": product.name, "score": score, "verdict": verdict, "is_market_data_verified": bool(product.evidence_url and product.evidence_checked_at), "weights": {"demand": 0.25, "competition": 0.15, "margin": 0.25, "supplier_reliability": 0.15, "fulfilment_fit": 0.10, "compliance_risk": 0.10}, "warning": "Score is decision support, not a sales forecast or guarantee."}


@app.post("/proposals")
def create_proposal(req: ProposalRequest, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_owner(x_admin_key)
    with closing(db()) as conn:
        duplicate = conn.execute("SELECT * FROM proposals WHERE idempotency_key=?", (req.idempotency_key,)).fetchone()
        if duplicate:
            return {"id": duplicate["id"], "status": duplicate["status"], "duplicate": True}
        cycle = current_cycle(conn)
        if not cycle or cycle["status"] != "active":
            raise HTTPException(409, "No active funding cycle. Discretionary actions are frozen.")
        totals = ledger_totals(conn, cycle["id"])
        loss = cycle_loss(conn, cycle)
        if loss >= cycle["loss_limit"]:
            raise HTTPException(409, "Loss limit reached. Discretionary actions are frozen.")
        if req.amount > totals["cash_available"]:
            raise HTTPException(409, "Proposal exceeds available cash.")
        loss_remaining = max(0.0, float(cycle["loss_limit"]) - loss)
        if req.amount > loss_remaining:
            raise HTTPException(409, f"Proposal exceeds remaining loss budget of {loss_remaining:.2f}.")
        if req.amount > DEFAULT_ACTION_CAP:
            raise HTTPException(409, f"Proposal exceeds per-action cap of {DEFAULT_ACTION_CAP:.2f}.")
        status = "pending"  # Approval always required in MVP; execution is not connected.
        proposal_id = str(uuid.uuid4())
        conn.execute("INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, NULL)", (proposal_id, req.kind, req.amount, status, req.rationale, req.idempotency_key, now()))
        conn.commit()
    audit("proposal_created", {"id": proposal_id, "kind": req.kind, "amount": req.amount, "status": status})
    return {"id": proposal_id, "status": status, "execution": "not_connected", "message": "Proposal recorded only; no purchase or payment was made."}


@app.post("/proposals/{proposal_id}/decision")
def decide_proposal(proposal_id: str, req: DecisionRequest, x_admin_key: str | None = Header(default=None)) -> dict[str, Any]:
    require_owner(x_admin_key)
    with closing(db()) as conn:
        proposal = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not proposal:
            raise HTTPException(404, "Proposal not found.")
        if proposal["status"] != "pending":
            raise HTTPException(409, "Proposal already resolved.")
        status = "approved_for_manual_execution" if req.decision == "approve" else "rejected"
        conn.execute("UPDATE proposals SET status=?, resolved_at=? WHERE id=?", (status, now(), proposal_id))
        conn.commit()
    audit("proposal_decision", {"id": proposal_id, "decision": req.decision})
    return {"id": proposal_id, "status": status, "message": "Approval does not execute an external transaction in this MVP."}


@app.get("/audit")
def get_audit(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    with closing(db()) as conn:
        rows = conn.execute("SELECT event, detail, created_at FROM audit ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
    return {"events": [{"event": r["event"], "detail": json.loads(r["detail"]), "created_at": r["created_at"]} for r in rows]}


@app.get("/policy")
def policy() -> dict[str, Any]:
    return {"execution_mode": EXECUTION_MODE, "loss_limit_pct": LOSS_LIMIT_PCT, "reinvestment_pct": REINVESTMENT_PCT, "per_action_cap": DEFAULT_ACTION_CAP, "external_integrations": [], "automatic_money_movement": False, "agent_policy": execution_policy(), "notes": ["No payment or marketplace integration is active.", "Set secure authentication before deployment.", "Owner approval is required for proposals."]}
