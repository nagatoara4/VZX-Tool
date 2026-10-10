"""Small durable task queue; intentionally no autonomous financial execution."""
from __future__ import annotations
import json, os, sqlite3, uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.getenv("COMMERCE_DB_PATH", "commerce.db")
ALLOWED_TASKS = {"product_research", "supplier_due_diligence", "profitability_analysis", "order_reconciliation", "daily_report"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def db() -> sqlite3.Connection:
    c=sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_queue() -> None:
    with closing(db()) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS agent_tasks(
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, task_type TEXT NOT NULL,
        payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status,created_at)")
        c.commit()


def enqueue(user_id: str, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task_type not in ALLOWED_TASKS:
        raise ValueError("Unsupported task type.")
    task_id=str(uuid.uuid4())
    init_queue()
    with closing(db()) as c:
        c.execute("INSERT INTO agent_tasks VALUES (?,?,?,?, 'queued', NULL, 0, ?, ?)",
                  (task_id,user_id,task_type,json.dumps(payload),now(),now()))
        c.commit()
    return {"id":task_id,"status":"queued","task_type":task_type}


def get_task(user_id: str, task_id: str) -> dict[str, Any] | None:
    init_queue()
    with closing(db()) as c:
        r=c.execute("SELECT * FROM agent_tasks WHERE id=? AND user_id=?",(task_id,user_id)).fetchone()
    return dict(r) if r else None


def execution_policy() -> dict[str, Any]:
    return {
      "autonomous_tasks": sorted(ALLOWED_TASKS),
      "financial_execution": False,
      "purchase_execution": False,
      "external_side_effects": False,
      "requires_owner_approval": ["inventory_purchase","advertising_spend","payment","refund","supplier_contract","marketplace_listing"],
      "note": "Queue stores requests. A worker provider and verified data/API integrations must be configured before jobs can run."
    }
