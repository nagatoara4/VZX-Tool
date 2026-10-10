"""Multi-user account and budget API for Autonomous Commerce OS.

This module records budgets and proposals per user. It does not custody or transfer money.
A verified payment-provider webhook must be implemented and reviewed before any payment
can ever be credited to a user's ledger.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, EmailStr, field_validator
from dotenv import load_dotenv

load_dotenv()
router = APIRouter(prefix="/api/v1", tags=["multi-user platform"])
DB_PATH = os.getenv("COMMERCE_DB_PATH", "commerce.db")
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))
LOSS_LIMIT_PCT = float(os.getenv("LOSS_LIMIT_PCT", "0.30"))
ACTION_CAP = float(os.getenv("DEFAULT_ACTION_CAP", "25.00"))
bearer = HTTPBearer(auto_error=False)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_platform_db() -> None:
    with closing(conn()) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS platform_users (
          id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
          status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_cycles (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, initial_capital REAL NOT NULL,
          loss_limit REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES platform_users(id)
        );
        CREATE TABLE IF NOT EXISTS user_ledger (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, cycle_id TEXT NOT NULL,
          kind TEXT NOT NULL, amount REAL NOT NULL, note TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'recorded', external_ref TEXT UNIQUE,
          created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES platform_users(id),
          FOREIGN KEY(cycle_id) REFERENCES user_cycles(id)
        );
        CREATE TABLE IF NOT EXISTS user_proposals (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL,
          amount REAL NOT NULL, rationale TEXT NOT NULL, status TEXT NOT NULL,
          idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(user_id, idempotency_key),
          FOREIGN KEY(user_id) REFERENCES platform_users(id)
        );
        CREATE TABLE IF NOT EXISTS platform_audit (
          id TEXT PRIMARY KEY, actor_id TEXT, event TEXT NOT NULL,
          detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_user ON user_ledger(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_proposals_user ON user_proposals(user_id, created_at);
        """)
        c.commit()


def audit(actor_id: str | None, event: str, detail: dict[str, Any]) -> None:
    with closing(conn()) as c:
        c.execute("INSERT INTO platform_audit VALUES (?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), actor_id, event, json.dumps(detail, sort_keys=True), utcnow()))
        c.commit()


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.urlsafe_b64encode(salt).decode().rstrip("=") + "." + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_s, digest_s = stored.split(".", 1)
        salt = base64.urlsafe_b64decode(salt_s + "=" * (-len(salt_s) % 4))
        expected = base64.urlsafe_b64decode(digest_s + "=" * (-len(digest_s) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def issue_token(user_id: str, role: str) -> str:
    if not AUTH_SECRET or len(AUTH_SECRET) < 32:
        raise HTTPException(503, "Authentication is not configured. Set AUTH_SECRET to a random secret of at least 32 characters.")
    header = b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",",":")).encode())
    payload = b64(json.dumps({"sub":user_id,"role":role,"exp":int(time.time())+TOKEN_TTL_SECONDS}, separators=(",",":")).encode())
    unsigned = header + "." + payload
    sig = b64(hmac.new(AUTH_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
    return unsigned + "." + sig


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    if not credentials:
        raise HTTPException(401, "Bearer token required.")
    if not AUTH_SECRET or len(AUTH_SECRET) < 32:
        raise HTTPException(503, "Authentication is not configured.")
    try:
        header, payload, signature = credentials.credentials.split(".")
        unsigned = header + "." + payload
        expected = b64(hmac.new(AUTH_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if int(claims["exp"]) < int(time.time()):
            raise ValueError("expired")
        with closing(conn()) as c:
            user = c.execute("SELECT id,email,display_name,role,status FROM platform_users WHERE id=?", (claims["sub"],)).fetchone()
        if not user or user["status"] != "active":
            raise ValueError("inactive")
        return dict(user)
    except Exception:
        raise HTTPException(401, "Invalid or expired bearer token.")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(x.islower() for x in v) or not any(x.isupper() for x in v) or not any(x.isdigit() for x in v):
            raise ValueError("Password must contain upper/lowercase letters and a digit.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class BudgetRequest(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    currency: Literal["USD"] = "USD"
    note: str = Field(default="Owner-declared budget", min_length=1, max_length=240)


class ProposalRequest(BaseModel):
    kind: Literal["sample_purchase", "inventory_purchase", "advertising", "tooling", "other"]
    amount: float = Field(gt=0, le=1_000_000)
    rationale: str = Field(min_length=10, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=120)


@router.get("/status")
def platform_status() -> dict[str, Any]:
    return {
        "service": "Autonomous Commerce OS",
        "multi_user_accounts": True,
        "account_isolation": "per-user database records",
        "budget_recording": "enabled",
        "payment_collection": "disabled_until_provider_and_legal_setup",
        "amazon_api": "not_connected",
        "supplier_apis": "not_connected",
        "background_agent": "proposal-only",
        "live_money_movement": False,
    }


@router.post("/auth/register", status_code=201)
def register(req: RegisterRequest) -> dict[str, Any]:
    with closing(conn()) as c:
        if c.execute("SELECT 1 FROM platform_users WHERE email=?", (req.email.lower(),)).fetchone():
            raise HTTPException(409, "An account with this email already exists.")
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO platform_users VALUES (?, ?, ?, ?, 'member', 'active', ?)",
                  (user_id, req.email.lower(), password_hash(req.password), req.display_name, utcnow()))
        c.commit()
    audit(user_id, "account_registered", {"email": req.email.lower()})
    return {"id": user_id, "email": req.email.lower(), "display_name": req.display_name, "status": "created", "next_step": "Log in to receive a bearer token."}


@router.post("/auth/login")
def login(req: LoginRequest) -> dict[str, Any]:
    with closing(conn()) as c:
        user = c.execute("SELECT * FROM platform_users WHERE email=?", (req.email.lower(),)).fetchone()
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    if user["status"] != "active":
        raise HTTPException(403, "Account is disabled.")
    token = issue_token(user["id"], user["role"])
    audit(user["id"], "login", {})
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"id": user["id"], "email": user["email"], "display_name": user["display_name"], "role": user["role"]}


@router.get("/account")
def account(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with closing(conn()) as c:
        cycles = c.execute("SELECT * FROM user_cycles WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        rows = c.execute("SELECT kind,amount,status FROM user_ledger WHERE user_id=?", (user["id"],)).fetchall()
        proposals = c.execute("SELECT COUNT(*) n FROM user_proposals WHERE user_id=? AND status='pending'", (user["id"],)).fetchone()["n"]
    deposited = sum(float(r["amount"]) for r in rows if r["kind"] == "deposit" and r["status"] == "confirmed")
    spent = sum(float(r["amount"]) for r in rows if r["kind"] in ("expense","purchase","refund_paid") and r["status"] == "confirmed")
    return {
        "user_id": user["id"],
        "currency": "USD",
        "confirmed_deposits": round(deposited,2),
        "confirmed_spend": round(spent,2),
        "recorded_balance": round(deposited-spent,2),
        "pending_proposals": proposals,
        "cycles": [{"id":r["id"],"initial_capital":r["initial_capital"],"loss_limit":r["loss_limit"],"status":r["status"],"created_at":r["created_at"]} for r in cycles],
        "warning": "Only verified confirmed ledger entries count. A budget request is not a payment or transfer."
    }


@router.post("/budget")
def create_budget(req: BudgetRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    # This is an intent/declaration only. It is never treated as money received.
    cycle_id = str(uuid.uuid4())
    with closing(conn()) as c:
        active = c.execute("SELECT id,status FROM user_cycles WHERE user_id=? AND status='active'", (user["id"],)).fetchone()
        if active:
            raise HTTPException(409, "You already have an active budget cycle. Close or review it before creating another.")
        c.execute("INSERT INTO user_cycles VALUES (?, ?, ?, ?, 'active', ?)",
                  (cycle_id, user["id"], req.amount, round(req.amount*LOSS_LIMIT_PCT,2), utcnow()))
        c.execute("INSERT INTO user_ledger VALUES (?, ?, ?, 'deposit', ?, ?, 'pending_payment', NULL, ?)",
                  (str(uuid.uuid4()), user["id"], cycle_id, req.amount, req.note, utcnow()))
        c.commit()
    audit(user["id"], "budget_declared_pending_payment", {"cycle_id":cycle_id,"amount":req.amount,"currency":req.currency})
    return {"cycle_id":cycle_id,"amount":req.amount,"currency":req.currency,"status":"pending_payment","loss_limit":round(req.amount*LOSS_LIMIT_PCT,2),"payment_url":None,"message":"Budget saved as pending only. No payment link exists and no funds have moved."}


@router.get("/ledger")
def ledger(user: dict[str, Any] = Depends(current_user), limit: int = 100) -> dict[str, Any]:
    limit = max(1,min(limit,500))
    with closing(conn()) as c:
        rows = c.execute("SELECT id,cycle_id,kind,amount,note,status,external_ref,created_at FROM user_ledger WHERE user_id=? ORDER BY created_at DESC LIMIT ?",(user["id"],limit)).fetchall()
    return {"entries":[dict(r) for r in rows]}


@router.post("/proposals")
def propose(req: ProposalRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with closing(conn()) as c:
        dup = c.execute("SELECT id,status FROM user_proposals WHERE user_id=? AND idempotency_key=?", (user["id"],req.idempotency_key)).fetchone()
        if dup:
            return {"id":dup["id"],"status":dup["status"],"duplicate":True}
        cycle = c.execute("SELECT * FROM user_cycles WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",(user["id"],)).fetchone()
        if not cycle:
            raise HTTPException(409,"Create a budget cycle first.")
        confirmed = c.execute("SELECT kind,amount FROM user_ledger WHERE user_id=? AND cycle_id=? AND status='confirmed'",(user["id"],cycle["id"])).fetchall()
        cash = sum(float(r["amount"]) for r in confirmed if r["kind"] in ("deposit","realized_income","refund_received")) - sum(float(r["amount"]) for r in confirmed if r["kind"] in ("expense","purchase","refund_paid","liability_reserved"))
        if cash <= 0:
            raise HTTPException(409,"No confirmed available cash. A declared budget is not available until payment is verified.")
        if req.amount > min(cash, ACTION_CAP, float(cycle["loss_limit"])):
            raise HTTPException(409,"Proposal exceeds confirmed cash, per-action cap, or loss budget.")
        pid=str(uuid.uuid4())
        c.execute("INSERT INTO user_proposals VALUES (?, ?, ?, ?, ?, 'pending_review', ?, ?)",
                  (pid,user["id"],req.kind,req.amount,req.rationale,req.idempotency_key,utcnow()))
        c.commit()
    audit(user["id"],"proposal_created",{"proposal_id":pid,"amount":req.amount,"kind":req.kind})
    return {"id":pid,"status":"pending_review","execution":"disabled","message":"Proposal created. No purchase or payment was executed."}


@router.get("/proposals")
def list_proposals(user: dict[str, Any] = Depends(current_user), limit: int = 100) -> dict[str, Any]:
    limit=max(1,min(limit,500))
    with closing(conn()) as c:
        rows=c.execute("SELECT id,kind,amount,rationale,status,created_at FROM user_proposals WHERE user_id=? ORDER BY created_at DESC LIMIT ?",(user["id"],limit)).fetchall()
    return {"proposals":[dict(r) for r in rows]}


@router.get("/integrations")
def integrations(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    # Presence-only checks: never reveal credential values.
    flags = {
      "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET")),
      "paypal_configured": bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET")),
      "amazon_sp_api_configured": all(os.getenv(k) for k in ("AMAZON_SP_API_REFRESH_TOKEN","AMAZON_SP_API_LWA_CLIENT_ID","AMAZON_SP_API_LWA_CLIENT_SECRET")),
      "aliexpress_api_configured": bool(os.getenv("ALIEXPRESS_APP_KEY") and os.getenv("ALIEXPRESS_APP_SECRET")),
      "alibaba_api_configured": bool(os.getenv("ALIBABA_APP_KEY") and os.getenv("ALIBABA_APP_SECRET")),
    }
    return {"providers":flags,"live_execution_enabled":False,"message":"Credentials alone do not prove country eligibility or grant API access. Integration remains disabled until sandbox tests, webhook verification, account approval, and compliance checks pass."}
