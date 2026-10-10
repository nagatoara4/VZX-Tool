"""Isolated simulation ledger. It never transfers real money or calls marketplaces."""
import os, sqlite3, uuid
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from platform_api import current_user

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation-only commerce"])
DB_PATH = os.getenv("COMMERCE_DB_PATH", "commerce.db")
def now(): return datetime.now(timezone.utc).isoformat()
def db():
    c=sqlite3.connect(DB_PATH, timeout=20, isolation_level=None); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA journal_mode=WAL"); return c
def cents(v: Decimal): return int((v.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)*100).to_integral_value())
def dollars(v: int): return round(v/100,2)
def init_simulation_db():
    with closing(db()) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sim_cash_events(
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,kind TEXT NOT NULL,amount_cents INTEGER NOT NULL,
          reference TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,reference));
        CREATE TABLE IF NOT EXISTS sim_orders(
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,product_name TEXT NOT NULL,quantity INTEGER NOT NULL,
          product_cost_cents INTEGER NOT NULL,shipping_budget_cents INTEGER NOT NULL,fee_budget_cents INTEGER NOT NULL,
          reserved_cents INTEGER NOT NULL,status TEXT NOT NULL,sale_price_cents INTEGER,actual_shipping_cents INTEGER,
          actual_fees_cents INTEGER,net_profit_cents INTEGER,created_at TEXT NOT NULL,settled_at TEXT,idempotency_key TEXT NOT NULL,
          UNIQUE(user_id,idempotency_key));
        CREATE INDEX IF NOT EXISTS idx_sim_cash_user ON sim_cash_events(user_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_sim_orders_user ON sim_orders(user_id,created_at);
        """)
def balance_cents(c,user_id):
    rows=c.execute("SELECT kind,amount_cents FROM sim_cash_events WHERE user_id=?",(user_id,)).fetchall()
    return sum(int(r["amount_cents"])*(1 if r["kind"] in ("seed","sale","release") else -1) for r in rows)

class SimCashRequest(BaseModel):
    amount_usd: Decimal=Field(gt=Decimal("0"),le=Decimal("100000"))
    reference: str=Field(min_length=8,max_length=120)
    note: str=Field(default="Sandbox-only simulated starting cash",min_length=1,max_length=240)
class SimOrderRequest(BaseModel):
    product_name: str=Field(min_length=2,max_length=160)
    quantity: int=Field(ge=1,le=10000)
    product_cost_usd: Decimal=Field(gt=Decimal("0"),le=Decimal("100000"))
    shipping_budget_usd: Decimal=Field(ge=Decimal("0"),le=Decimal("100000"))
    fee_budget_usd: Decimal=Field(ge=Decimal("0"),le=Decimal("100000"))
    idempotency_key: str=Field(min_length=8,max_length=120)
class SimSettleRequest(BaseModel):
    sale_price_usd: Decimal=Field(gt=Decimal("0"),le=Decimal("1000000"))
    actual_shipping_usd: Decimal=Field(ge=Decimal("0"),le=Decimal("100000"))
    actual_fees_usd: Decimal=Field(ge=Decimal("0"),le=Decimal("100000"))

@router.post("/cash",status_code=201)
def seed_cash(req:SimCashRequest,user:dict[str,Any]=Depends(current_user)):
    """Create fictional test cash, never a real deposit."""
    amount=cents(req.amount_usd)
    with closing(db()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            old=c.execute("SELECT id,amount_cents,kind FROM sim_cash_events WHERE user_id=? AND reference=?",(user["id"],req.reference)).fetchone()
            if old:
                if old["kind"]!="seed" or int(old["amount_cents"])!=amount: raise HTTPException(409,"Reference already used.")
                c.commit(); return {"id":old["id"],"status":"duplicate","simulation_only":True,"available_balance_usd":dollars(balance_cents(c,user["id"]))}
            eid=str(uuid.uuid4())
            c.execute("INSERT INTO sim_cash_events VALUES(?,?, 'seed',?,?,?,?)",(eid,user["id"],amount,req.reference,req.note,now()))
            c.commit()
        except Exception: c.rollback(); raise
        balance=balance_cents(c,user["id"])
    return {"id":eid,"status":"recorded","simulation_only":True,"currency":"USD","available_balance_usd":dollars(balance),
            "warning":"Fictional sandbox cash only; not a payment, deposit, or withdrawable balance."}

@router.get("/account")
def sim_account(user:dict[str,Any]=Depends(current_user)):
    with closing(db()) as c:
        bal=balance_cents(c,user["id"]); orders=c.execute("SELECT status,net_profit_cents FROM sim_orders WHERE user_id=?",(user["id"],)).fetchall()
    return {"mode":"simulation_only","currency":"USD","available_balance_usd":dollars(bal),
            "orders_total":len(orders),"orders_open":sum(o["status"]=="reserved" for o in orders),
            "settled_orders":sum(o["status"]=="settled" for o in orders),
            "realized_net_profit_usd":dollars(sum(int(o["net_profit_cents"] or 0) for o in orders if o["status"]=="settled")),
            "notice":"Simulated figures only. No live payment, purchase, sale, or withdrawal occurred."}

@router.get("/orders")
def list_orders(user:dict[str,Any]=Depends(current_user)):
    with closing(db()) as c: rows=c.execute("SELECT * FROM sim_orders WHERE user_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
    out=[]
    for row in rows:
        x=dict(row)
        for k in ("product_cost","shipping_budget","fee_budget","reserved"): x[k+"_usd"]=dollars(x[k+"_cents"])
        for k in ("sale_price","actual_shipping","actual_fees","net_profit"): x[k+"_usd"]=dollars(x[k+"_cents"]) if x[k+"_cents"] is not None else None
        out.append(x)
    return {"orders":out}

@router.post("/orders",status_code=201)
def create_order(req:SimOrderRequest,user:dict[str,Any]=Depends(current_user)):
    cost=cents(req.product_cost_usd)*req.quantity; shipping=cents(req.shipping_budget_usd); fees=cents(req.fee_budget_usd)
    reserve=cost+shipping+fees; oid=req.idempotency_key
    with closing(db()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            dup=c.execute("SELECT id,status FROM sim_orders WHERE user_id=? AND idempotency_key=?",(user["id"],oid)).fetchone()
            if dup: c.commit(); return {"id":dup["id"],"status":dup["status"],"duplicate":True,"simulation_only":True}
            bal=balance_cents(c,user["id"])
            if reserve>bal: raise HTTPException(409,"Insufficient simulated cash: need {:.2f} USD, available {:.2f} USD.".format(dollars(reserve),dollars(bal)))
            c.execute("INSERT INTO sim_orders VALUES(?,?,?,?,?,?,?,?,'reserved',NULL,NULL,NULL,NULL,?,?,?)",
                      (str(uuid.uuid4()),user["id"],req.product_name,req.quantity,cost,shipping,fees,reserve,now(),None,oid))
            c.execute("INSERT INTO sim_cash_events VALUES(?,?, 'reserve',?,?,?,?)",(str(uuid.uuid4()),user["id"],reserve,"reserve:"+oid,"Simulated order reserve "+oid,now()))
            c.commit()
        except Exception: c.rollback(); raise
        bal=balance_cents(c,user["id"])
    return {"id":oid,"status":"reserved","simulation_only":True,"reserved_usd":dollars(reserve),"available_balance_usd":dollars(bal),
            "message":"Reserved in simulation only; no supplier or marketplace was contacted."}

@router.post("/orders/{order_id}/settle")
def settle_order(order_id:str,req:SimSettleRequest,user:dict[str,Any]=Depends(current_user)):
    shipping=cents(req.actual_shipping_usd); fees=cents(req.actual_fees_usd); sale=cents(req.sale_price_usd)
    with closing(db()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            o=c.execute("SELECT * FROM sim_orders WHERE id=? AND user_id=?",(order_id,user["id"])).fetchone()
            if not o: raise HTTPException(404,"Simulated order not found.")
            if o["status"]=="settled":
                c.commit(); return {"id":order_id,"status":"settled","duplicate":True,"net_profit_usd":dollars(o["net_profit_cents"])}
            if o["status"]!="reserved": raise HTTPException(409,"Order is not settleable.")
            total=int(o["product_cost_cents"])+shipping+fees
            if total>int(o["reserved_cents"]): raise HTTPException(409,"Actual costs exceed reserved budget.")
            profit=sale-total; release=int(o["reserved_cents"])-total
            if release: c.execute("INSERT INTO sim_cash_events VALUES(?,?, 'release',?,?,?,?)",(str(uuid.uuid4()),user["id"],release,"release:"+order_id,"Unused simulated reserve",now()))
            c.execute("INSERT INTO sim_cash_events VALUES(?,?, 'sale',?,?,?,?)",(str(uuid.uuid4()),user["id"],sale,"sale:"+order_id,"Simulated sale proceeds",now()))
            c.execute("UPDATE sim_orders SET status='settled',sale_price_cents=?,actual_shipping_cents=?,actual_fees_cents=?,net_profit_cents=?,settled_at=? WHERE id=? AND user_id=?",
                      (sale,shipping,fees,profit,now(),order_id,user["id"]))
            c.commit()
        except Exception: c.rollback(); raise
        bal=balance_cents(c,user["id"])
    return {"id":order_id,"status":"settled","simulation_only":True,"sale_price_usd":dollars(sale),"total_cost_usd":dollars(total),
            "net_profit_usd":dollars(profit),"available_balance_usd":dollars(bal),"message":"Simulated profit only, not real-world income."}
