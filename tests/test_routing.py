from agent_cost_governor.ledger import BudgetLedger
from agent_cost_governor.policy import DowngradeRule, Policy, TenantPolicy
from agent_cost_governor.routing import decide


def _policy() -> Policy:
    acme = TenantPolicy(
        name="acme",
        daily_budget_usd=10.0,
        block_at_pct=1.0,
        alert_at_pct=0.8,
        downgrade=[DowngradeRule(from_model="gpt-4o", to_model="gpt-4o-mini", threshold_pct=0.8)],
    )
    defaults = TenantPolicy(name="__defaults__", daily_budget_usd=2.0)
    return Policy(pricing={}, tenants={"acme": acme}, defaults=defaults)


def test_allow_when_well_under_budget():
    led = BudgetLedger()
    d = decide({"model": "gpt-4o"}, "acme", _policy(), led)
    assert d.allowed is True
    assert d.downgraded is False
    assert d.chosen_model == "gpt-4o"


def test_downgrade_when_over_threshold():
    led = BudgetLedger()
    led.record("acme", 8.5)  # 85% of 10
    d = decide({"model": "gpt-4o"}, "acme", _policy(), led)
    assert d.allowed is True
    assert d.downgraded is True
    assert d.chosen_model == "gpt-4o-mini"
    assert d.alert is True


def test_block_when_at_or_above_budget():
    led = BudgetLedger()
    led.record("acme", 10.0)
    d = decide({"model": "gpt-4o"}, "acme", _policy(), led)
    assert d.allowed is False
    assert d.blocked_reason == "daily_budget_exhausted"


def test_unknown_tenant_uses_defaults():
    led = BudgetLedger()
    d = decide({"model": "gpt-4o"}, "stranger", _policy(), led)
    assert d.allowed is True
    assert d.budget_usd == 2.0


def test_no_downgrade_for_other_models():
    led = BudgetLedger()
    led.record("acme", 9.5)
    d = decide({"model": "claude-3.5"}, "acme", _policy(), led)
    assert d.allowed is True
    assert d.downgraded is False
    assert d.chosen_model == "claude-3.5"
    assert d.alert is True
