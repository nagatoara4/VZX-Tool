import pytest
from agent_engine import analyze_opportunity, enforce_cycle_limits, verified_profit_alert


def sample_product(**overrides):
    value = {
        "product_id": "sample-001", "unit_cost": "10", "shipping_per_unit": "2",
        "marketplace_fee_per_unit": "3", "tax_per_unit": "1", "expected_sale_price": "30",
        "units": 2, "demand_score": 90, "competition_score": 20,
        "supplier_reliability": 90, "compliance_risk": 10,
    }
    value.update(overrides)
    return value


def test_strong_product_scores_with_all_costs_included():
    result = analyze_opportunity(sample_product(), available_budget=100, max_order_spend=100)
    assert result.currency == "USD"
    assert result.landed_cost_per_unit == "16.00"
    assert result.expected_profit_total == "28.00"
    assert result.decision == "strong_candidate_requires_authorized_execution"


def test_budget_and_cap_fail_closed():
    result = analyze_opportunity(sample_product(), available_budget=20, max_order_spend=20)
    assert result.decision == "reject_or_review"
    assert any("budget" in reason for reason in result.reasons)
    assert any("cap" in reason for reason in result.reasons)


def test_compliance_risk_blocks_even_high_demand():
    result = analyze_opportunity(sample_product(compliance_risk=90), available_budget=100, max_order_spend=100)
    assert result.decision == "reject_or_review"


def test_cycle_guard_blocks_spend_past_loss_limit():
    result = enforce_cycle_limits(cycle_capital=100, realized_net_pnl=-9, proposed_spend=2,
                                  max_loss_pct=0.10, max_order_spend=25)
    assert result["allowed"] is False


def test_cycle_guard_allows_spend_within_limits():
    result = enforce_cycle_limits(cycle_capital=100, realized_net_pnl=0, proposed_spend=10,
                                  max_loss_pct=0.10, max_order_spend=25)
    assert result["allowed"] is True


def test_profit_alert_requires_reconciled_settlement():
    with pytest.raises(ValueError):
        verified_profit_alert(amount=10, order_id="order-1", payment_settled=False, costs_reconciled=True)
    alert = verified_profit_alert(amount="10.50", order_id="order-1", payment_settled=True, costs_reconciled=True)
    assert alert["message"] == "+$10.50 net profit confirmed"
