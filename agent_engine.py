"""Bounded commerce opportunity analysis. No payments, scraping, or purchases are executed here."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Money values must be valid decimals.") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("Money values must be finite and non-negative.")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Opportunity:
    product_id: str
    currency: str
    units: int
    landed_cost_per_unit: str
    expected_revenue_per_unit: str
    expected_profit_total: str
    margin_pct: float
    roi_pct: float
    score: float
    decision: str
    reasons: list[str]


def analyze_opportunity(
    product: dict[str, Any],
    *,
    available_budget: Any,
    max_order_spend: Any,
    max_loss_pct: float = 0.10,
    minimum_margin_pct: float = 20.0,
    minimum_roi_pct: float = 25.0,
) -> Opportunity:
    """Score a product using user-supplied/verified estimates; estimates are not guarantees.

    Required product keys: product_id, unit_cost, shipping_per_unit, marketplace_fee_per_unit,
    tax_per_unit, expected_sale_price, units, demand_score, competition_score,
    supplier_reliability, compliance_risk. Scores are 0..100.
    """
    budget, cap = money(available_budget), money(max_order_spend)
    if not 0 <= max_loss_pct <= 1:
        raise ValueError("max_loss_pct must be between 0 and 1.")
    units = product.get("units")
    if not isinstance(units, int) or isinstance(units, bool) or units < 1:
        raise ValueError("units must be a positive integer.")
    fields = ("demand_score", "competition_score", "supplier_reliability", "compliance_risk")
    for field in fields:
        value = product.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError(f"{field} must be between 0 and 100.")

    unit_cost = money(product["unit_cost"])
    shipping = money(product["shipping_per_unit"])
    fees = money(product["marketplace_fee_per_unit"])
    tax = money(product["tax_per_unit"])
    price = money(product["expected_sale_price"])
    landed = unit_cost + shipping + fees + tax
    spend = landed * units
    profit_per_unit = price - landed
    profit_total = profit_per_unit * units
    margin = float((profit_per_unit / price * 100) if price else Decimal(0))
    roi = float((profit_per_unit / landed * 100) if landed else Decimal(0))
    # Conservative weighted score; compliance and supplier risk dominate.
    score = (
        float(product["demand_score"]) * 0.25
        + (100 - float(product["competition_score"])) * 0.10
        + float(product["supplier_reliability"]) * 0.20
        + max(0.0, min(100.0, margin)) * 0.20
        + max(0.0, min(100.0, roi / 2)) * 0.10
        + (100 - float(product["compliance_risk"])) * 0.15
    )
    reasons: list[str] = []
    if spend > budget:
        reasons.append("order exceeds confirmed available budget")
    if spend > cap:
        reasons.append("order exceeds per-order spending cap")
    if profit_per_unit <= 0:
        reasons.append("estimated unit economics are not profitable")
    if margin < minimum_margin_pct:
        reasons.append("estimated margin is below the configured minimum")
    if roi < minimum_roi_pct:
        reasons.append("estimated ROI is below the configured minimum")
    if product["supplier_reliability"] < 70:
        reasons.append("supplier reliability is below threshold")
    if product["compliance_risk"] >= 60:
        reasons.append("compliance risk requires rejection or manual review")
    if reasons:
        decision = "reject_or_review"
    elif score >= 75:
        decision = "strong_candidate_requires_authorized_execution"
    else:
        decision = "watchlist"
    return Opportunity(
        product_id=str(product["product_id"]),
        currency="USD",
        units=units,
        landed_cost_per_unit=str(landed.quantize(CENT)),
        expected_revenue_per_unit=str(price),
        expected_profit_total=str(profit_total.quantize(CENT)),
        margin_pct=round(margin, 2),
        roi_pct=round(roi, 2),
        score=round(score, 2),
        decision=decision,
        reasons=reasons,
    )


def enforce_cycle_limits(
    *,
    cycle_capital: Any,
    realized_net_pnl: Any,
    proposed_spend: Any,
    max_loss_pct: float,
    max_order_spend: Any,
) -> dict[str, Any]:
    """Fail-closed guard. Realized P&L must come from reconciled records, not estimates."""
    capital = money(cycle_capital)
    pnl = Decimal(str(realized_net_pnl))
    spend, order_cap = money(proposed_spend), money(max_order_spend)
    if not pnl.is_finite():
        raise ValueError("realized_net_pnl must be finite.")
    if not 0 <= max_loss_pct <= 1:
        raise ValueError("max_loss_pct must be between 0 and 1.")
    loss_limit = capital * Decimal(str(max_loss_pct))
    realized_loss = max(Decimal(0), -pnl)
    remaining_loss_budget = max(Decimal(0), loss_limit - realized_loss)
    allowed = (
        capital > 0
        and realized_loss < loss_limit
        and spend <= order_cap
        and spend <= capital
        and spend <= remaining_loss_budget
    )
    return {
        "allowed": bool(allowed),
        "currency": "USD",
        "cycle_capital": str(capital),
        "realized_net_pnl": str(pnl.quantize(CENT)),
        "loss_limit": str(loss_limit.quantize(CENT)),
        "remaining_loss_budget": str(remaining_loss_budget.quantize(CENT)),
        "proposed_spend": str(spend),
        "reason": "within configured limits" if allowed else "blocked by budget, per-order cap, or loss stop",
    }


def verified_profit_alert(*, amount: Any, order_id: str, payment_settled: bool, costs_reconciled: bool) -> dict[str, str]:
    """Only emit profit notifications when the order is settled and all costs are reconciled."""
    value = Decimal(str(amount))
    if not value.is_finite():
        raise ValueError("Profit amount must be finite.")
    if not payment_settled or not costs_reconciled:
        raise ValueError("Cannot report realized profit before settlement and cost reconciliation.")
    if value <= 0:
        raise ValueError("Profit alert requires positive realized net profit.")
    if not order_id.strip():
        raise ValueError("order_id is required for auditability.")
    return {
        "type": "realized_net_profit",
        "currency": "USD",
        "amount": str(value.quantize(CENT, rounding=ROUND_HALF_UP)),
        "order_id": order_id,
        "message": f"+${value.quantize(CENT, rounding=ROUND_HALF_UP)} net profit confirmed",
    }


def as_dict(opportunity: Opportunity) -> dict[str, Any]:
    return asdict(opportunity)
