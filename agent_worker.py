"""Durable queue with an explicitly bounded analysis-only worker.

No card data, payment calls, supplier orders, or marketplace side effects are performed.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv

load_dotenv()
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


def process_one() -> dict[str, Any] | None:
    """Process one queued analysis task. Returns None if the queue is empty."""
    init_queue()
    with closing(db()) as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute("SELECT * FROM agent_tasks WHERE status='queued' ORDER BY created_at ASC LIMIT 1").fetchone()
        if not task:
            c.commit()
            return None
        c.execute("UPDATE agent_tasks SET status='running', attempts=attempts+1, updated_at=? WHERE id=? AND status='queued'", (now(),task["id"]))
        c.commit()
    payload = json.loads(task["payload"])
    try:
        if task["task_type"] == "profitability_analysis":
            from agent_engine import analyze_opportunity, as_dict
            candidates = payload.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError("Supply payload.candidates with verified product cost, shipping, fees, tax, price, demand, supplier reliability and compliance fields.")
            budget = payload.get("available_budget")
            cap = payload.get("max_order_spend")
            if budget is None or cap is None:
                raise ValueError("Supply available_budget and max_order_spend in USD.")
            results = [as_dict(analyze_opportunity(item, available_budget=budget, max_order_spend=cap)) for item in candidates]
            results.sort(key=lambda x: (x["decision"] == "strong_candidate_requires_authorized_execution", x["score"]), reverse=True)
            result = {"mode":"analysis_only","currency":"USD","candidates_analyzed":len(results),"ranked_opportunities":results,"execution":"disabled"}
            status = "completed"
        elif task["task_type"] == "order_reconciliation":
            result = {"mode":"validation_only","message":"No provider order records supplied or connected. Reconciliation was not performed.","execution":"disabled"}
            status = "blocked_missing_connector"
        else:
            result = {"mode":"connector_required","message":f"No approved live data connector is configured for task type '{task['task_type']}'. Provide verified data or connect an approved provider.","execution":"disabled"}
            status = "blocked_missing_connector"
    except (ValueError, KeyError, TypeError) as exc:
        result = {"mode":"input_validation","error":str(exc),"execution":"disabled"}
        status = "failed_validation"
    with closing(db()) as c:
        c.execute("UPDATE agent_tasks SET status=?, result=?, updated_at=? WHERE id=? AND status='running'",
                  (status,json.dumps(result,sort_keys=True),now(),task["id"]))
        c.commit()
    return {"id":task["id"],"status":status,"result":result}


def execution_policy() -> dict[str, Any]:
    return {
      "autonomous_tasks": sorted(ALLOWED_TASKS),
      "financial_execution": False,
      "purchase_execution": False,
      "external_side_effects": False,
      "worker_mode": "analysis_only",
      "requires_owner_approval": ["inventory_purchase","advertising_spend","payment","refund","supplier_contract","marketplace_listing"],
      "note": "Worker can rank user-supplied candidate data for profitability analysis. Live research, card control and purchases require approved official connectors and independent go-live checks."
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process one queued VZX analysis task.")
    parser.add_argument("--once", action="store_true", help="Process at most one queued task and exit.")
    args = parser.parse_args()
    result = process_one()
    print(json.dumps(result or {"status":"idle","message":"No queued tasks."}, indent=2))
